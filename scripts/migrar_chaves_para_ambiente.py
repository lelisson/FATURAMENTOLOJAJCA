"""Move as chaves dos arquivos .env para variáveis de ambiente do usuário do Windows (HKCU\\Environment).

- .env do painel (filial): OMIE_APP_KEY/SECRET → OMIE_FILIAL_APP_KEY/SECRET; PAINEL_DATA_KEY → PAINEL_DATA_KEY

Só remove as linhas dos .env depois de conferir que o valor gravado é idêntico. Nunca imprime valores.
Uso: python scripts/migrar_chaves_para_ambiente.py
"""
import ctypes
import sys
import winreg
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV_PAINEL = ROOT / ".env"

PLANO = [  # (arquivo, nome no .env, variável do usuário)
    (ENV_PAINEL, "OMIE_APP_KEY", "OMIE_FILIAL_APP_KEY"),
    (ENV_PAINEL, "OMIE_APP_SECRET", "OMIE_FILIAL_APP_SECRET"),
    (ENV_PAINEL, "PAINEL_DATA_KEY", "PAINEL_DATA_KEY"),
]


def ler_usuario(nome: str) -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, nome)[0])
    except OSError:
        return ""


def gravar_usuario(nome: str, valor: str) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, nome, 0, winreg.REG_SZ, valor)


def remover_linhas(arquivo: Path, nomes: set[str]) -> None:
    texto = arquivo.read_text(encoding="utf-8")
    manter = [
        linha for linha in texto.splitlines()
        if linha.split("=", 1)[0].strip().removeprefix("export ").strip() not in nomes
    ]
    arquivo.write_text("\n".join(manter) + "\n", encoding="utf-8")


def main() -> int:
    valores = {arq: dotenv_values(arq) if arq.exists() else {} for arq in {ENV_PAINEL}}
    remover: dict[Path, set[str]] = {}
    erros = 0
    for arq, nome_env, var in PLANO:
        valor = (valores[arq].get(nome_env) or "").strip().strip('"')
        atual = ler_usuario(var)
        if not valor:
            print(f"{var}: {'já está no ambiente' if atual else 'AUSENTE no .env e no ambiente'}")
            erros += not atual
            continue
        if atual and atual != valor:
            print(f"{var}: já existe com outro valor; não alterado ({arq.name} mantido)")
            erros += 1
            continue
        gravar_usuario(var, valor)
        if ler_usuario(var) != valor:
            print(f"{var}: falha na conferência; {arq.name} mantido")
            erros += 1
            continue
        print(f"{var}: gravado e conferido")
        remover.setdefault(arq, set()).add(nome_env)

    for arq, nomes in remover.items():
        remover_linhas(arq, nomes)
        print(f"Removidas de {arq}: {', '.join(sorted(nomes))}")

    # Avisa o Windows (Explorer, novos terminais) que o ambiente mudou.
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)
    return 1 if erros else 0


if __name__ == "__main__":
    sys.exit(main())
