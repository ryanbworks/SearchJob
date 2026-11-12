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

# Como aprender/demonstrar cada requisito (usado nas recomendações do painel).
SKILL_TIPS: dict[str, str] = {
    "Windows": "Pratique instalação, drivers, contas e restauração do sistema. "
    "Escreva 'suporte a Windows 10/11' no currículo.",
    "Linux": "Suba uma VM Debian/Ubuntu no Proxmox e pratique comandos, usuários e permissões.",
    "macOS": "Noções básicas bastam: a documentação de suporte da Apple cobre o essencial.",
    "Microsoft 365 / Office": "Trilha gratuita 'Microsoft 365 Fundamentals' (MS-900) no "
    "Microsoft Learn.",
    "Active Directory": "Monte um laboratório com Windows Server (avaliação gratuita) no Proxmox: "
    "crie usuários, grupos e GPOs e resete senhas.",
    "Azure / Entra ID / Intune": "Trilhas gratuitas AZ-900 e SC-900 no Microsoft Learn.",
    "Redes (TCP/IP)": "Curso gratuito 'Networking Basics' da Cisco Networking Academy.",
    "DNS / DHCP": "Configure DNS e DHCP no seu laboratório (Windows Server ou pfSense) e "
    "documente o passo a passo no GitHub.",
    "VPN / Firewall": "Instale pfSense/OPNsense numa VM, crie regras e uma VPN WireGuard.",
    "Cabeamento estruturado": "Aprenda os padrões T568A/B e a crimpagem: é rápido e prático.",
    "Hardware / manutenção": "Cite montagens e manutenções que você já fez. O curso Google IT "
    "Support cobre bem o tema.",
    "Impressoras": "Saiba instalar driver, compartilhar na rede e destravar filas de impressão.",
    "Telefonia / VoIP": "Noções de PABX/VoIP: o FreePBX numa VM é um bom laboratório.",
    "Android / iOS": "Pratique configurar e-mail corporativo, Wi-Fi e MDM básico em celulares.",
    "Acesso remoto": "Use AnyDesk, TeamViewer e RDP e cite as ferramentas no currículo.",
    "Ferramentas de chamados (ITSM)": "Suba o GLPI no Proxmox (Docker) e simule abrir, "
    "priorizar e fechar chamados.",
    "ITIL": "Estude o ITIL 4 Foundation (há resumos e simulados gratuitos). A certificação "
    "é um diferencial forte.",
    "Virtualização": "Seu homelab com Proxmox já conta: descreva-o no currículo.",
    "Backup": "Agende backups no Proxmox e teste a restauração. Isso vira um bom exemplo "
    "para entrevistas.",
    "SQL / banco de dados": "SQLBolt e o curso de SQL da Fundação Bradesco são gratuitos.",
    "Scripts (PowerShell / Python)": "Automatize uma tarefa real em PowerShell ou Python e "
    "publique no GitHub.",
    "Atendimento ao usuário": "Destaque experiências com público, mesmo fora de TI: "
    "comunicação pesa muito em suporte.",
    "Inglês": "Leia documentação técnica todos os dias e informe seu nível real.",
    "Ensino superior": "Informe 'cursando' com a previsão de conclusão: muitas vagas aceitam.",
    "CNH": "Exigida em field service. Sem CNH, priorize vagas internas ou remotas.",
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
