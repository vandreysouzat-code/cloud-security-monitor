import os
import socket
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def enviar_email(destinatario, assunto, mensagem):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")

    if not smtp_server:
        raise RuntimeError("SMTP_SERVER não configurado.")

    if not smtp_user:
        raise RuntimeError("SMTP_USER não configurado.")

    if not smtp_password:
        raise RuntimeError("SMTP_PASSWORD não configurado.")

    email = EmailMessage()
    email["From"] = smtp_user
    email["To"] = destinatario
    email["Subject"] = assunto
    email.set_content(mensagem)

    endereco_original = socket.getaddrinfo

    def resolver_ipv4(host, port, *args, **kwargs):
        return endereco_original(
            host,
            port,
            socket.AF_INET,
            socket.SOCK_STREAM
        )

    socket.getaddrinfo = resolver_ipv4

    try:
        with smtplib.SMTP(
            smtp_server,
            smtp_port,
            timeout=15
        ) as servidor:

            servidor.ehlo()
            servidor.starttls()
            servidor.ehlo()
            servidor.login(
                smtp_user,
                smtp_password
            )
            servidor.send_message(email)

    finally:
        socket.getaddrinfo = endereco_original

    print(f"📧 E-mail enviado para {destinatario}")


if __name__ == "__main__":
    print("📧 Serviço de e-mail carregado corretamente.")