def analisar_expiracao_ssl(dias_restantes):
    if dias_restantes is None:
        return {
            "nivel": "DESCONHECIDO",
            "mensagem": "Não foi possível determinar a validade do certificado."
        }

    if dias_restantes <= 0:
        return {
            "nivel": "EXPIRADO",
            "mensagem": "O certificado SSL está expirado."
        }

    if dias_restantes <= 7:
        return {
            "nivel": "CRÍTICO",
            "mensagem": f"O certificado SSL expira em {dias_restantes} dias."
        }

    if dias_restantes <= 15:
        return {
            "nivel": "ALERTA",
            "mensagem": f"O certificado SSL expira em {dias_restantes} dias."
        }

    if dias_restantes <= 30:
        return {
            "nivel": "ATENÇÃO",
            "mensagem": f"O certificado SSL expira em {dias_restantes} dias."
        }

    return {
        "nivel": "NORMAL",
        "mensagem": f"O certificado SSL possui {dias_restantes} dias restantes."
    }


if __name__ == "__main__":
    testes = [60, 31, 30, 20, 15, 10, 7, 3, 1, 0, -1]

    for dias in testes:
        resultado = analisar_expiracao_ssl(dias)

        print(
            f"{dias} dias -> "
            f"{resultado['nivel']} | "
            f"{resultado['mensagem']}"
        )

    