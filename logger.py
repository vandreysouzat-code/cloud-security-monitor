def salvar_monitor(mensagem):

    with open("logs/monitor.log", "a") as arquivo:

        arquivo.write(mensagem + "\n")


def salvar_seguranca(mensagem):

    with open("logs/security.log", "a") as arquivo:

        arquivo.write(mensagem + "\n")