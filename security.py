def verificar_alerta(
    falhas_consecutivas,
    estado_anterior,
    limite_falhas
):

    if (
        falhas_consecutivas == 1
        and estado_anterior == "NORMAL"
    ):

        return "WARNING"


    elif (
        falhas_consecutivas >= limite_falhas
        and estado_anterior != "CRITICAL"
    ):

        return "CRITICAL"


    elif (
        falhas_consecutivas == 0
        and estado_anterior != "NORMAL"
    ):

        return "RECOVERY"


    return None