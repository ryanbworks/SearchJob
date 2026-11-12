from searchjob.skills import extract_skills, normalize


def test_normalize_removes_accents():
    assert normalize("Manutenção de Hardware") == "manutencao de hardware"


def test_extract_common_support_skills():
    text = """
    Atendimento ao usuário N1 via GLPI, suporte a Windows 10/11 e Microsoft 365.
    Conhecimento em Active Directory, DNS e DHCP. Desejável ITIL e inglês básico.
    """
    skills = extract_skills(text)
    for expected in [
        "Windows",
        "Microsoft 365 / Office",
        "Active Directory",
        "DNS / DHCP",
        "Ferramentas de chamados (ITSM)",
        "ITIL",
        "Inglês",
        "Atendimento ao usuário",
    ]:
        assert expected in skills


def test_does_not_match_partial_words():
    # "windowsill" não deve virar "Windows"; "iosmart" não deve virar "Android / iOS"
    assert extract_skills("windowsill iosmart") == []
