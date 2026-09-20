#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
instalar_radioberry_juice.py
=============================

Instalador/compilador automatico do Radioberry "Juice" (firmware-extended)
para Windows (x64 e/ou x86).

Baseado, comando a comando, em:
  - juice/firmware-extended/BUILD-README.md
  - juice/firmware-extended/FTDI-WINDOWS-README
  (repositorio: https://github.com/pa3gsb/Radioberry-2.x, pasta
   juice/firmware-extended)

O que este script faz, por esta ordem, verificando SEMPRE primeiro se
cada coisa ja esta instalada antes de instalar/alterar algo:

  1. Confirma que esta a correr em Windows e localiza a pasta do codigo-fonte
     (juice/firmware-extended, a que contem o windows-Makefile).
  2. Verifica se o MSYS2 esta instalado em C:\\msys64 (ou noutra pasta indicada);
     se nao estiver, descarrega o instalador oficial e instala-o.
  3. Actualiza o MSYS2 (pacman -Syu) e verifica/instala os pacotes GCC/G++
     do MinGW-w64 (x86_64 e, opcionalmente, i686) e o GNU make.
  4. Garante que as pastas dos compiladores estao no PATH do utilizador
     (sem duplicar entradas ja existentes).
  5. Verifica se o driver FTDI D2XX 2.12.36.20 esta instalado; se nao
     estiver, descarrega o pacote oficial da FTDI e lanca o instalador.
  6. Compila o firmware com "make -f windows-Makefile ARCH=x64" e/ou
     "ARCH=x86", tal como descrito no BUILD-README.md.
  7. Confirma que os executaveis e a pasta "dist" ficaram criados.

O script e' idempotente: pode ser corrido varias vezes sem repetir
trabalho ja feito (cada passo comeca por verificar o estado actual).

IMPORTANTE
----------
- Este script corre em Windows (usa PowerShell/cmd, MSYS2 e o instalador
  da FTDI). Nao corre em Linux/macOS.
- A instalacao do driver FTDI normalmente pede privilegios de
  administrador; o script deteta isso e avisa.
- Nao foi possivel testar este script num Windows real a partir deste
  ambiente (sandbox Linux); reveja a saida de cada passo antes de usar
  o executavel final com o radio ligado. Se algum passo falhar, o
  script para e explica exactamente o que falhou, em vez de continuar
  "as cegas".

Uso tipico (a partir da pasta juice/firmware-extended, em PowerShell ou cmd):

    python instalar_radioberry_juice.py                 # compila so x64
    python instalar_radioberry_juice.py --arch both      # x64 e x86
    python instalar_radioberry_juice.py --arch x86
    python instalar_radioberry_juice.py --skip-ftdi-driver
    python instalar_radioberry_juice.py --yes            # nao pergunta nada

"""

from __future__ import annotations

import argparse
import ctypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# --------------------------------------------------------------------------
# Configuracao / constantes
# --------------------------------------------------------------------------

MSYS2_INSTALLER_URL = (
    "https://github.com/msys2/msys2-installer/releases/latest/"
    "download/msys2-x86_64-latest.exe"
)

# Pacote oficial com o instalador do driver FTDI D2XX (ver
# FTDI-WINDOWS-README do projecto).
FTDI_DRIVER_ZIP_URL = (
    "https://ftdichip.com/wp-content/uploads/2025/03/CDM2123620_Setup.zip"
)
FTDI_DRIVER_VERSION = "2.12.36.20"

MINGW_PACKAGES = {
    "x64": "mingw-w64-x86_64-gcc",
    "x86": "mingw-w64-i686-gcc",
}
MINGW_BIN_SUBDIR = {
    "x64": r"mingw64\bin",
    "x86": r"mingw32\bin",
}
CXX_EXE = {
    "x64": "x86_64-w64-mingw32-g++.exe",
    "x86": "i686-w64-mingw32-g++.exe",
}

# O windows-Makefile usa sintaxe de cmd.exe nas suas regras (por exemplo
# "if not exist ... mkdir", "copy /Y ...") — o BUILD-README avisa
# explicitamente para NAO usar uma shell Linux com este Makefile. Por
# isso usamos aqui o GNU make do MinGW-w64 (pacote "mingw-w64-x86_64-make",
# binario "mingw32-make.exe"), que e' um executavel Windows nativo e usa
# cmd.exe para correr as regras — NAO o "make" base do MSYS2, que traria
# "sh.exe" para o mesmo PATH e podia levar o make a escolher uma shell
# Unix por engano, partindo a compilacao. E' exactamente o cenario que o
# BUILD-README refere quando diz "If GNU Make is named mingw32-make on
# your system, replace make with mingw32-make."
MAKE_PACOTE = "mingw-w64-x86_64-make"
MAKE_EXE_NOME = "mingw32-make.exe"

REQUIRED_SOURCE_FILES = [
    "windows-Makefile",
    "radioberry.c",
    "gateware.c",
    "stream.c",
    "register.c",
    "pa.c",
    "radioberry.props",
]


# --------------------------------------------------------------------------
# Utilitarios genericos
# --------------------------------------------------------------------------

class InstaladorError(RuntimeError):
    """Erro irrecuperavel do instalador; a mensagem e' mostrada ao utilizador."""


def log(msg: str) -> None:
    print(f"[radioberry-juice] {msg}", flush=True)


def passo(titulo: str) -> None:
    print(f"\n=== {titulo} ===", flush=True)


def confirmar(pergunta: str, auto_sim: bool) -> bool:
    """Pede confirmacao ao utilizador, a menos que --yes tenha sido usado."""
    if auto_sim:
        return True
    resposta = input(f"{pergunta} [S/n] ").strip().lower()
    return resposta in ("", "s", "sim", "y", "yes")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run(cmd, cwd=None, check=True, env=None, capture=False):
    """
    Corre um comando (lista de argumentos, sem shell=True) e devolve o
    CompletedProcess. Regista o comando para diagnostico.
    """
    log("A correr: " + " ".join(str(c) for c in cmd) + (f"  (cwd={cwd})" if cwd else ""))
    kwargs = {}
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.STDOUT
        kwargs["text"] = True
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, **kwargs)


def download(url: str, destino: Path, tentativas: int = 3) -> Path:
    """
    Descarrega um ficheiro com um User-Agent de browser normal (alguns
    servidores, incluindo o da FTDI, recusam o User-Agent por omissao do
    Python com HTTP 403) e algumas tentativas em caso de falha de rede
    transitoria.
    """
    log(f"A descarregar {url}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    pedido = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "radioberry-juice-installer/1.0"
            )
        },
    )
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            with urllib.request.urlopen(pedido, timeout=60) as resposta:
                with open(destino, "wb") as ficheiro:
                    shutil.copyfileobj(resposta, ficheiro)
            log(f"Guardado em {destino}")
            return destino
        except Exception as erro:  # rede instavel, proxy, DNS, TLS, etc.
            ultimo_erro = erro
            log(f"Falha ao descarregar (tentativa {tentativa}/{tentativas}): {erro}")

    raise InstaladorError(
        f"Nao consegui descarregar {url} apos {tentativas} tentativas "
        f"({ultimo_erro}). Verifique a ligacao a internet/firewall/proxy, "
        "ou descarregue o ficheiro manualmente e indique-o ao script."
    )


# --------------------------------------------------------------------------
# Passo 0: pre-requisitos e localizacao da pasta do codigo-fonte
# --------------------------------------------------------------------------

def verificar_windows() -> None:
    if platform.system() != "Windows":
        raise InstaladorError(
            "Este script serve para compilar o Radioberry Juice PARA Windows "
            "e deve ser corrido dentro do Windows (PowerShell ou cmd.exe), "
            "nao em Linux/macOS/WSL. Se estiver a usar WSL/Ubuntu, siga antes "
            "a seccao 'Cross-compiling for Raspberry Pi' ou construa "
            "directamente numa maquina Windows."
        )


def localizar_pasta_fonte(caminho_indicado: str | None) -> Path:
    """
    Encontra a pasta juice/firmware-extended (a que contem windows-Makefile).
    Por omissao usa a pasta onde este script esta guardado; se nao encontrar
    ai, tenta a pasta actual de trabalho.
    """
    candidatos = []
    if caminho_indicado:
        candidatos.append(Path(caminho_indicado))
    candidatos.append(Path(__file__).resolve().parent)
    candidatos.append(Path.cwd())

    for pasta in candidatos:
        if (pasta / "windows-Makefile").is_file():
            return pasta

    raise InstaladorError(
        "Nao encontrei 'windows-Makefile' em nenhuma das pastas verificadas: "
        + ", ".join(str(c) for c in candidatos)
        + ". Corra este script de dentro de juice/firmware-extended, ou "
        "indique o caminho com --repo-dir CAMINHO."
    )


def verificar_ficheiros_fonte(pasta_fonte: Path) -> None:
    em_falta = [f for f in REQUIRED_SOURCE_FILES if not (pasta_fonte / f).exists()]
    if em_falta:
        raise InstaladorError(
            f"A pasta {pasta_fonte} nao parece ser um checkout completo de "
            f"juice/firmware-extended: faltam os ficheiros {em_falta}."
        )
    for rbf in ("gateware/CL016/radioberry.rbf", "gateware/CL025/radioberry.rbf"):
        if not (pasta_fonte / rbf).exists():
            raise InstaladorError(
                f"Falta o ficheiro de gateware '{rbf}' em {pasta_fonte}. "
                "Verifique se o .zip/checkout esta completo (a pasta gateware/ "
                "tem de conter os .rbf de CL016 e CL025)."
            )
    log(f"Pasta de codigo-fonte confirmada: {pasta_fonte}")


# --------------------------------------------------------------------------
# Passo 1: MSYS2
# --------------------------------------------------------------------------

def msys2_instalado(msys2_root: Path) -> bool:
    return (msys2_root / "usr" / "bin" / "bash.exe").is_file() and (
        msys2_root / "usr" / "bin" / "pacman.exe"
    ).is_file()


def instalar_msys2(msys2_root: Path, auto_sim: bool) -> None:
    if msys2_instalado(msys2_root):
        log(f"MSYS2 ja esta instalado em {msys2_root} — a saltar instalacao.")
        return

    if not confirmar(
        f"O MSYS2 nao foi encontrado em {msys2_root}. Descarregar e instalar agora?",
        auto_sim,
    ):
        raise InstaladorError(
            "MSYS2 e' necessario para compilar (fornece o GCC/G++ do MinGW-w64 "
            "e o make). Instalacao cancelada pelo utilizador."
        )

    with tempfile.TemporaryDirectory() as tmp:
        instalador = download(MSYS2_INSTALLER_URL, Path(tmp) / "msys2-installer.exe")
        # Sintaxe oficial de instalacao nao-interactiva (confirmada em
        # https://www.msys2.org/docs/installer/ e no README do
        # https://github.com/msys2/msys2-installer): o subcomando e' "in"
        # (nao "install"), e sao precisos AMBOS os parametros
        # --confirm-command e --accept-messages para que nao apareca
        # nenhuma janela a pedir confirmacao. O caminho e' passado com "/"
        # tal como no exemplo oficial (o instalador aceita esse formato
        # em Windows sem problema).
        run(
            [
                str(instalador),
                "in",
                "--confirm-command",
                "--accept-messages",
                "--root",
                msys2_root.as_posix(),
            ]
        )

    if not msys2_instalado(msys2_root):
        raise InstaladorError(
            f"A instalacao do MSYS2 terminou mas nao encontrei bash.exe/pacman.exe "
            f"em {msys2_root}. Verifique manualmente (pode ter sido necessario "
            "aceitar um pedido do Windows / UAC)."
        )
    log("MSYS2 instalado com sucesso.")


def bash_msys2(msys2_root: Path, comando_shell: str, check: bool = True):
    """
    Corre um comando dentro do bash do MSYS2 (login shell), replicando o
    que o utilizador faria ao abrir 'MSYS2 MSYS' e escrever o comando.
    """
    bash_exe = msys2_root / "usr" / "bin" / "bash.exe"
    if not bash_exe.is_file():
        raise InstaladorError(f"Nao encontrei {bash_exe}; o MSYS2 esta instalado?")
    return run([str(bash_exe), "-lc", comando_shell], check=check, capture=True)


def actualizar_msys2(msys2_root: Path) -> None:
    """
    Equivalente a correr 'pacman -Syu' repetidamente ate nao haver mais nada
    para actualizar, tal como o FTDI-WINDOWS-README pede (o pacman pode
    pedir para fechar/reabrir o terminal quando actualiza o proprio
    msys2-runtime; aqui isso corresponde apenas a repetir o comando).
    """
    passo("A actualizar o MSYS2 (pacman -Syu)")
    for tentativa in range(1, 6):
        resultado = bash_msys2(msys2_root, "pacman -Syu --noconfirm", check=False)
        saida = resultado.stdout or ""
        print(saida)
        if resultado.returncode != 0:
            raise InstaladorError(
                "'pacman -Syu' falhou. Corra manualmente 'MSYS2 MSYS' e "
                "'pacman -Syu' para ver o erro completo."
            )
        # O pacman devolve esta mensagem no idioma do sistema; em Ingles e'
        # "nothing to do", em Portugues (como confirmado numa execucao real
        # deste script) e' "nada a fazer" — cobrimos ambas as variantes.
        saida_lower = saida.lower()
        if "nothing to do" in saida_lower or "nada a fazer" in saida_lower:
            log("MSYS2 ja estava actualizado.")
            return
        log(f"Actualizacao {tentativa}/5 concluida; a repetir para confirmar.")
    log("MSYS2 actualizado (numero maximo de repeticoes atingido, a continuar).")


def pacote_instalado(msys2_root: Path, pacote: str) -> bool:
    resultado = bash_msys2(msys2_root, f"pacman -Qi {pacote}", check=False)
    return resultado.returncode == 0


def instalar_pacote(msys2_root: Path, pacote: str) -> None:
    if pacote_instalado(msys2_root, pacote):
        log(f"Pacote '{pacote}' ja esta instalado — a saltar.")
        return

    for tentativa in (1, 2):
        log(f"A instalar o pacote '{pacote}' (tentativa {tentativa}/2)...")
        resultado = bash_msys2(
            msys2_root, f"pacman -S --needed --noconfirm {pacote}", check=False
        )
        print(resultado.stdout or "")
        if resultado.returncode == 0 and pacote_instalado(msys2_root, pacote):
            log(f"Pacote '{pacote}' instalado com sucesso.")
            return
        if tentativa == 1:
            # Causa mais comum de falha na 1a tentativa: indices de
            # pacotes desactualizados ou chaveiro (keyring) desactualizado
            # numa instalacao MSYS2 muito recente. Um refresh simples
            # costuma resolver antes de desistir.
            log("Primeira tentativa falhou; a actualizar indices do pacman e a tentar de novo...")
            bash_msys2(msys2_root, "pacman -Sy --noconfirm", check=False)

    raise InstaladorError(
        f"Falha ao instalar o pacote '{pacote}' via pacman, mesmo apos "
        "actualizar os indices. Verifique a ligacao a internet e tente "
        f"correr manualmente em 'MSYS2 MSYS': pacman -S --needed {pacote}"
    )


def preparar_toolchain(msys2_root: Path, arquiteturas: list[str]) -> None:
    passo("A verificar/instalar o compilador (GCC/G++ MinGW-w64) e o make")
    # mingw32-make.exe (ver comentario junto a MAKE_PACOTE) e' instalado
    # sempre, independentemente da arquitectura escolhida, porque e' a
    # ferramenta "make" usada para invocar o Makefile em qualquer dos casos.
    instalar_pacote(msys2_root, MAKE_PACOTE)
    for arch in arquiteturas:
        instalar_pacote(msys2_root, MINGW_PACKAGES[arch])


# --------------------------------------------------------------------------
# Passo 2: PATH do utilizador
# --------------------------------------------------------------------------

def obter_path_utilizador() -> str:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as chave:
        try:
            valor, _ = winreg.QueryValueEx(chave, "Path")
            return valor
        except FileNotFoundError:
            return ""


def definir_path_utilizador(novo_valor: str) -> None:
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
    ) as chave:
        winreg.SetValueEx(chave, "Path", 0, winreg.REG_EXPAND_SZ, novo_valor)

    # Avisa o resto do Windows (Explorer, novos terminais) de que o
    # ambiente mudou, tal como o Windows faz quando se usa 'setx'.
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x1A
    SMTO_ABORTIFHUNG = 0x0002
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None
    )


def garantir_path(msys2_root: Path, arquiteturas: list[str]) -> list[str]:
    """
    Garante que as pastas necessarias (mingw64\\bin — onde fica o
    mingw32-make.exe — e, se pedido, mingw32\\bin para o compilador x86)
    estao no PATH do utilizador, sem duplicar entradas ja existentes.
    Devolve a lista de pastas que ficaram garantidas (para tambem serem
    usadas nesta sessao do script).

    Propositadamente NAO se adiciona "usr\\bin" do MSYS2 ao PATH: essa
    pasta contem "sh.exe", e ter uma shell Unix no PATH pode levar o GNU
    make a tentar correr as regras do windows-Makefile (que sao de
    cmd.exe) atraves dessa shell, partindo a compilacao — ver o
    comentario junto a MAKE_PACOTE.
    """
    passo("A verificar o PATH do utilizador")
    pastas_necessarias = [str(msys2_root / MINGW_BIN_SUBDIR["x64"])]  # traz o mingw32-make.exe
    for arch in arquiteturas:
        pasta = str(msys2_root / MINGW_BIN_SUBDIR[arch])
        if pasta not in pastas_necessarias:
            pastas_necessarias.append(pasta)

    path_actual = obter_path_utilizador()
    partes_actuais = [p for p in path_actual.split(";") if p]
    partes_normalizadas = {p.strip().lower().rstrip("\\") for p in partes_actuais}

    a_adicionar = [
        p for p in pastas_necessarias
        if p.strip().lower().rstrip("\\") not in partes_normalizadas
    ]

    if a_adicionar:
        log("A adicionar ao PATH do utilizador: " + "; ".join(a_adicionar))
        novo_path = ";".join(partes_actuais + a_adicionar)
        definir_path_utilizador(novo_path)
    else:
        log("PATH do utilizador ja contem todas as pastas necessarias.")

    # Actualiza tambem o ambiente do PROCESSO ACTUAL, para que os passos
    # seguintes (make, g++) funcionem já nesta mesma execucao do script,
    # sem ser preciso abrir um terminal novo.
    for pasta in pastas_necessarias:
        if pasta.lower() not in os.environ.get("PATH", "").lower():
            os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")

    return pastas_necessarias


# --------------------------------------------------------------------------
# Passo 3: driver FTDI D2XX
# --------------------------------------------------------------------------

def driver_ftdi_instalado() -> bool:
    """
    Verifica se o driver FTDI 2.12.36.20 ja esta instalado, correndo
    'pnputil /enum-drivers' tal como descrito no FTDI-WINDOWS-README, e
    procurando a versao esperada no texto devolvido.
    """
    try:
        resultado = run(
            ["pnputil", "/enum-drivers"], check=False, capture=True
        )
    except FileNotFoundError:
        log("Nao consegui correr 'pnputil' — a saltar verificacao automatica do driver FTDI.")
        return False
    saida = resultado.stdout or ""
    return ("FTDI" in saida) and (FTDI_DRIVER_VERSION in saida)


def instalar_driver_ftdi(auto_sim: bool) -> None:
    passo("A verificar o driver FTDI D2XX")
    if driver_ftdi_instalado():
        log(f"Driver FTDI {FTDI_DRIVER_VERSION} ja esta instalado — a saltar.")
        return

    log(
        f"Driver FTDI {FTDI_DRIVER_VERSION} nao foi detectado "
        "(ou a versao instalada e' diferente)."
    )
    if not confirmar(
        "Descarregar e lancar o instalador oficial da FTDI agora?", auto_sim
    ):
        log(
            "Instalacao do driver FTDI ignorada. O programa compilado nao "
            "vai reconhecer o radio sem este driver — instale-o manualmente "
            "a partir de https://ftdichip.com/drivers/d2xx-drivers/ antes de usar."
        )
        return

    if not is_admin():
        log(
            "AVISO: este processo nao tem privilegios de administrador. "
            "O instalador da FTDI vai provavelmente pedir uma confirmacao "
            "de UAC (Controlo de Conta de Utilizador) — aceite-a quando aparecer."
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = download(FTDI_DRIVER_ZIP_URL, tmp_path / "CDM_Setup.zip")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_path)

        candidatos_exe = sorted(tmp_path.rglob("*.exe"))
        if not candidatos_exe:
            raise InstaladorError(
                f"O pacote descarregado de {FTDI_DRIVER_ZIP_URL} nao contem "
                "nenhum .exe. Instale o driver manualmente a partir de "
                "https://ftdichip.com/drivers/d2xx-drivers/"
            )
        # Se houver mais do que um .exe no pacote (por exemplo um
        # uninstaller), preferir o que tem "setup" no nome.
        com_setup = [e for e in candidatos_exe if "setup" in e.name.lower()]
        instalador_exe = com_setup[0] if com_setup else candidatos_exe[0]
        if len(candidatos_exe) > 1:
            log(
                "Mais do que um .exe encontrado no pacote da FTDI: "
                + ", ".join(e.name for e in candidatos_exe)
                + f" — a usar '{instalador_exe.name}'."
            )
        log(f"A lancar o instalador da FTDI: {instalador_exe.name}")
        log(
            "Se aparecer uma janela do instalador da FTDI, siga as instrucoes "
            "no ecra (Seguinte/Instalar/Concluir)."
        )
        # O instalador da FTDI e' interactivo (janela grafica); nao existe
        # uma opcao silenciosa documentada e fiavel para esta versao, por
        # isso lanca-se a janela e espera-se que o utilizador a conclua.
        run([str(instalador_exe)], check=True)

    if driver_ftdi_instalado():
        log("Driver FTDI instalado e confirmado com sucesso.")
    else:
        log(
            "Nao consegui confirmar automaticamente a instalacao do driver "
            "(isto pode acontecer mesmo com a instalacao bem sucedida, "
            "dependendo da versao do Windows). Pode verificar manualmente com:\n"
            "  pnputil /enum-drivers | Select-String -Pattern \"FTDI\" -Context 5,5"
        )


# --------------------------------------------------------------------------
# Passo 4: compilacao
# --------------------------------------------------------------------------

def compilador_disponivel(msys2_root: Path, arch: str) -> bool:
    exe = msys2_root / MINGW_BIN_SUBDIR[arch] / CXX_EXE[arch]
    return exe.is_file()


def compilar(pasta_fonte: Path, msys2_root: Path, arch: str) -> Path:
    passo(f"A compilar para {arch}")

    if not compilador_disponivel(msys2_root, arch):
        raise InstaladorError(
            f"O compilador {CXX_EXE[arch]} nao foi encontrado em "
            f"{msys2_root / MINGW_BIN_SUBDIR[arch]}. A instalacao do "
            "pacote MinGW-w64 falhou ou ficou incompleta."
        )

    # Caminho deterministico para o mingw32-make.exe (ver comentario junto
    # a MAKE_PACOTE): evita depender da ordem do PATH do sistema, onde
    # outro "make"/"sh" (por exemplo do Git for Windows) possa interferir.
    make_exe_path = msys2_root / MINGW_BIN_SUBDIR["x64"] / MAKE_EXE_NOME
    if make_exe_path.is_file():
        make_exe = str(make_exe_path)
    else:
        make_exe = shutil.which(MAKE_EXE_NOME) or shutil.which("make")
        if not make_exe:
            raise InstaladorError(
                f"Nao encontrei '{MAKE_EXE_NOME}' em {make_exe_path} nem no PATH. "
                f"O pacote '{MAKE_PACOTE}' foi instalado correctamente?"
            )

    exe_dist = pasta_fonte / f"dist/windows-{arch}/radioberry-juice-{arch}.exe"

    run(
        [make_exe, "-f", "windows-Makefile", "clean-" + arch],
        cwd=pasta_fonte,
        check=False,  # 'clean-*' pode nao ter nada para limpar; nao e' erro
    )
    run(
        [make_exe, "-f", "windows-Makefile", f"ARCH={arch}"],
        cwd=pasta_fonte,
    )

    if not exe_dist.is_file():
        raise InstaladorError(
            f"A compilacao terminou sem erros aparentes mas nao encontrei "
            f"'{exe_dist}'. Verifique a saida do 'make' acima."
        )

    log(f"Compilacao concluida: {exe_dist}")
    return exe_dist


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def analisar_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Instala automaticamente tudo o que e' preciso (MSYS2, "
            "MinGW-w64, driver FTDI) e compila o Radioberry Juice "
            "(firmware-extended) para Windows, verificando sempre primeiro "
            "se cada componente ja esta instalado."
        )
    )
    parser.add_argument(
        "--arch",
        choices=["x64", "x86", "both"],
        default="x64",
        help="Arquitectura a compilar (por omissao: x64).",
    )
    parser.add_argument(
        "--repo-dir",
        default=None,
        help=(
            "Caminho para a pasta juice/firmware-extended. Por omissao usa "
            "a pasta onde este script esta guardado, ou a pasta actual."
        ),
    )
    parser.add_argument(
        "--msys2-root",
        default=r"C:\msys64",
        help=r"Pasta de instalacao do MSYS2 (por omissao: C:\msys64).",
    )
    parser.add_argument(
        "--skip-ftdi-driver",
        action="store_true",
        help="Nao verificar/instalar o driver FTDI D2XX.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Nao pedir confirmacao antes de instalar componentes (modo automatico).",
    )
    return parser.parse_args()


def main() -> int:
    args = analisar_argumentos()

    try:
        verificar_windows()

        pasta_fonte = localizar_pasta_fonte(args.repo_dir)
        verificar_ficheiros_fonte(pasta_fonte)

        arquiteturas = ["x64", "x86"] if args.arch == "both" else [args.arch]

        msys2_root = Path(args.msys2_root)

        passo("MSYS2")
        instalar_msys2(msys2_root, args.yes)
        actualizar_msys2(msys2_root)
        preparar_toolchain(msys2_root, arquiteturas)
        garantir_path(msys2_root, arquiteturas)

        if not args.skip_ftdi_driver:
            instalar_driver_ftdi(args.yes)
        else:
            log("A saltar verificacao do driver FTDI (--skip-ftdi-driver).")

        executaveis = []
        for arch in arquiteturas:
            executaveis.append(compilar(pasta_fonte, msys2_root, arch))

        passo("Concluido")
        for exe in executaveis:
            log(f"Executavel pronto: {exe}")
        log(
            "Antes de correr o programa, edite o 'radioberry.props' na pasta "
            "dist correspondente (call=, locator=, fpga=CL016 ou fpga=CL025) "
            "e garanta que o driver FTDI e as DLLs de runtime do MinGW "
            "estao acessiveis, conforme o BUILD-README.md."
        )
        return 0

    except InstaladorError as erro:
        print(f"\nERRO: {erro}\n", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as erro:
        print(f"\nERRO: o comando falhou (codigo {erro.returncode}): {erro}\n", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelado pelo utilizador.", file=sys.stderr)
        return 130
    except PermissionError as erro:
        print(
            f"\nERRO de permissoes: {erro}\n"
            "Isto acontece tipicamente se a pasta do MSYS2 (--msys2-root) "
            "nao pode ser criada/escrita pelo utilizador actual, ou se o "
            "instalador da FTDI precisa de privilegios de administrador. "
            "Tente correr o PowerShell/cmd 'Como Administrador' e repita.\n",
            file=sys.stderr,
        )
        return 1
    except Exception as erro:  # ultimo recurso: nunca mostrar so um traceback em bruto
        print(
            f"\nERRO inesperado ({type(erro).__name__}): {erro}\n"
            "Isto nao devia acontecer; copie esta mensagem se pedir ajuda.\n",
            file=sys.stderr,
        )
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
