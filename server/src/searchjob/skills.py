"""Extração de requisitos por palavras-chave.

Funciona sem IA: é rápida, determinística e alimenta o painel
"o que o mercado está pedindo". A IA complementa com uma análise mais fina.
"""

from __future__ import annotations

import re
import unicodedata

# nome exibido -> padrões (aplicados sobre texto minúsculo e sem acentos)
SKILL_PATTERNS: dict[str, list[str]] = {
    "Windows": [r"\bwindows\b"],
    "Linux": [r"\blinux\b", r"\bubuntu\b", r"\bdebian\b", r"\bred ?hat\b"],
    "macOS": [r"\bmac ?os\b", r"\bmacbook\b"],
    "Microsoft 365 / Office": [r"\boffice\b", r"\bm365\b", r"microsoft 365", r"\bexcel\b"],
    "Active Directory": [r"active directory", r"\bgpo\b"],
    "Azure / Entra ID / Intune": [r"\bazure\b", r"\bentra\b", r"\bintune\b"],
    "Redes (TCP/IP)": [r"\bredes\b", r"\btcp/?ip\b", r"\bnetwork"],
    "DNS / DHCP": [r"\bdns\b", r"\bdhcp\b"],
    "VPN / Firewall": [r"\bvpn\b", r"\bfirewall\b", r"\bfortinet\b", r"\bpfsense\b"],
    "Cabeamento estruturado": [r"cabeamento", r"\bcrimp"],
    "Hardware / manutenção": [r"hardware", r"manutencao (de|em) (micro|computador|equipamento)",
                              r"microinformatica", r"montagem"],
    "Impressoras": [r"impressora"],
    "Telefonia / VoIP": [r"telefonia", r"\bvoip\b", r"\bpabx\b"],
    "Android / iOS": [r"\bandroid\b", r"\bios\b", r"\biphone\b"],
    "Acesso remoto": [r"anydesk", r"teamviewer", r"acesso remoto", r"\brdp\b"],
    "Ferramentas de chamados (ITSM)": [r"\bglpi\b", r"\bjira\b", r"servicenow", r"\botrs\b",
                                       r"\bitsm\b", r"freshdesk", r"zendesk", r"chamados?"],
    "ITIL": [r"\bitil\b"],
    "Virtualização": [r"vmware", r"hyper-?v", r"proxmox", r"virtualiza"],
    "Backup": [r"\bbackup"],
    "SQL / banco de dados": [r"\bsql\b", r"banco de dados", r"\bmysql\b", r"postgres"],
    "Scripts (PowerShell / Python)": [r"powershell", r"\bpython\b", r"\bbash\b", r"\bscript"],
    "Atendimento ao usuário": [r"atendimento", r"service desk", r"help ?desk", r"\bn1\b",
                               r"nivel 1"],
    "Inglês": [r"\bingles\b", r"\benglish\b"],
    "Ensino superior": [r"ensino superior", r"graduacao", r"cursando", r"\bfaculdade\b"],
    "CNH": [r"\bcnh\b", r"carteira de habilitacao"],
}

_COMPILED = {
    name: [re.compile(p) for p in patterns] for name, patterns in SKILL_PATTERNS.items()
}


def normalize(text: str) -> str:
    """Minúsculas e sem acentos, para comparar palavras-chave com segurança."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def extract_skills(text: str) -> list[str]:
    norm = normalize(text)
    return [name for name, patterns in _COMPILED.items() if any(p.search(norm) for p in patterns)]
