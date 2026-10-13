# 🛡️ Cloud Security Monitor

**Monitoramento de disponibilidade, desempenho e certificados SSL de websites — executado localmente no seu computador.**

Projeto criado por **Victor Andrey** para estudar e praticar desenvolvimento de sistemas, Python, monitoramento web e fundamentos de segurança. O repositório é público; qualquer pessoa pode baixar o código e executar uma cópia local seguindo os passos abaixo.

> **Importante:** esta é uma aplicação local em desenvolvimento. Ao executar `launch.py`, o dashboard fica disponível no computador de quem iniciou o programa em `http://127.0.0.1:5000`. O projeto não oferece, por si só, uma instância hospedada para visitantes externos.

## ✨ Recursos

- Cadastro e login local, com sessões e proteção CSRF.
- Cadastro de websites por conta e visualização dos dados associados ao usuário autenticado.
- Verificações de disponibilidade e tempo de resposta.
- Monitoramento de certificados SSL e alertas.
- Dashboard, API e área administrativa.
- Validação de destinos monitorados para bloquear URLs locais, IPs literais, nomes internos, portas não padrão e respostas DNS privadas/reservadas.
- **Marca de autoria** no dashboard e nas telas principais: “Desenvolvido por Victor Andrey”.
- Botão **Compartilhar** que aponta para este repositório do GitHub, não para o `localhost` do computador de quem está executando.

As funcionalidades ainda podem mudar durante o desenvolvimento. Faça testes antes de usar em cenários importantes.

## 🧰 Tecnologias

- Python 3.12 (recomendado)
- Flask
- Requests
- SQLite para uso local
- PostgreSQL como opção para uma futura implantação de produção
- Waitress
- Docker / Docker Compose (opcional)

## 🚀 Executar no Windows (PowerShell / VS Code)

### 1. Pré-requisitos

Instale Python 3.12 ou compatível e Git. Durante a instalação do Python, habilite a opção para adicioná-lo ao PATH, se disponível.

### 2. Baixar o projeto

```powershell
git clone https://github.com/vandreysouzat-code/cloud-security-monitor.git
cd cloud-security-monitor
```

Se baixou o ZIP pelo GitHub, extraia-o e abra a pasta `cloud-security-monitor` no VS Code.

### 3. Criar e ativar o ambiente virtual

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se `py -3.12` não existir, verifique a versão instalada com `py --list` e use o lançador correspondente à sua instalação.

### 4. Criar sua configuração local

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copie o valor aleatório impresso e use-o como `SECRET_KEY` dentro de `.env`. Substitua também `ADMIN_INITIAL_PASSWORD` por uma senha forte e exclusiva. Para uso local, deixe `DATABASE_URL=` vazio para usar SQLite. Não compartilhe nem envie seu `.env` ao GitHub.

Abra o arquivo de configuração no VS Code, se necessário:

```powershell
code .env
```

### 5. Iniciar o dashboard

```powershell
python launch.py
```

Acesse no navegador:

**http://127.0.0.1:5000**

Para encerrar, volte ao terminal e pressione `Ctrl + C`.

## 🐧 Executar no Linux / macOS

```bash
git clone https://github.com/vandreysouzat-code/cloud-security-monitor.git
cd cloud-security-monitor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Edite `.env`, definindo uma `SECRET_KEY` aleatória e uma senha administrativa forte. Depois execute `python launch.py` e abra `http://127.0.0.1:5000`.

## 🏷️ Autoria, marca d'água e divulgação

O dashboard e as telas principais exibem **“Desenvolvido por Victor Andrey”** e links para os perfis do autor. O botão **Compartilhar** divulga o repositório público, para que outra pessoa possa encontrá-lo, baixar o código e executar a própria cópia.

- **GitHub:** https://github.com/vandreysouzat-code
- **Repositório:** https://github.com/vandreysouzat-code/cloud-security-monitor
- **LinkedIn:** https://www.linkedin.com/in/vandrey/

A marca faz parte dos arquivos protegidos pela assinatura da versão oficial. Na inicialização, o programa valida uma assinatura Ed25519 e os hashes SHA-256 dos arquivos; se a marca ou outro arquivo protegido for alterado, removido ou acrescentado, a inicialização é bloqueada e o programa informa que a cópia não corresponde à versão oficial assinada. A licença abaixo também exige atribuição.

**Limite técnico:** como o código-fonte é distribuído, uma pessoa determinada ainda pode editar o próprio verificador ou remover a checagem. Isso não torna essa cópia uma versão oficial nem concede autoria sobre o projeto original. A assinatura é uma forma de detectar adulterações comuns, não uma garantia de que qualquer modificação seja impossível.

### Assinatura de releases (somente para o autor original)

Na primeira publicação protegida, o autor deve executar no repositório original:

```powershell
python tools/sign_release.py --init
```

O script cria uma chave Ed25519 privada protegida por senha fora do repositório, em `~/.csm-signing/` (no Windows, `%USERPROFILE%\.csm-signing\`), fixa a chave pública no código e gera `release-manifest.json` e `release-manifest.sig`. **Nunca envie a chave privada ou sua senha ao GitHub nem compartilhe esses arquivos privados.** Faça uma cópia de segurança offline da chave privada e guarde a senha separadamente. Publique apenas o código com a chave pública fixada, o manifesto e a assinatura.

Depois que a versão assinada estiver no GitHub, quem clonar o projeto não precisa da chave privada: a aplicação valida a assinatura automaticamente ao iniciar. Em futuras versões do autor, após terminar todas as alterações, use `python tools/sign_release.py --sign` com a chave oficial existente antes de fazer commit e push. Não use `--init` para substituir uma chave oficial perdida; restaure o backup da chave original.

## 🔐 Segurança e dados

- A cópia local usa o banco SQLite da própria máquina.
- Não monitore sites sem autorização ou finalidade legítima.
- O validador bloqueia destinos locais/internos comuns; nenhuma validação isolada garante segurança absoluta contra todos os cenários de DNS ou rede. Revise a segurança antes de expor a aplicação a entradas não confiáveis.
- Não exponha a aplicação, o banco ou o arquivo `.env` à internet.
- Para uma implantação hospedada, será necessário fazer configuração adicional: PostgreSQL persistente, HTTPS, segredos de produção, limites antiabuso compartilhados, gestão de backups, monitoramento e revisão de segurança.

## 🧪 Testes

Com o ambiente virtual ativado:

```powershell
python -m unittest discover -s tests -v
```

## 📁 Estrutura principal

```text
cloud-security-monitor/
├── api.py
├── launch.py
├── database.py
├── monitor.py
├── ssl_monitor.py
├── scheduler.py
├── alerts.py
├── billing.py
├── url_safety.py
├── release_integrity.py
├── release-manifest.json       # gerado e assinado pelo autor
├── release-manifest.sig        # assinatura da versao oficial
├── tools/
│   └── sign_release.py         # ferramenta do autor; nao contem a chave privada
├── templates/
│   ├── dashboard.html
│   ├── login.html
│   ├── register.html
│   ├── admin.html
│   ├── planos.html
│   └── _creator_brand.html
├── tests/
│   ├── test_url_safety.py
│   └── test_release_integrity.py
├── requirements.txt
├── .env.example
├── .gitattributes
├── LICENSE
└── README.md
```

## 📜 Licença de uso

Este projeto é gratuito para execução local em contextos pessoais, educacionais e não comerciais conforme a **CSM Community Use License** incluída neste repositório. A licença exige manter a atribuição visível e os avisos de autoria ao redistribuir cópias e não concede permissão automática para vender o software ou oferecê-lo como serviço comercial.

**Transparência:** essa é uma licença personalizada de uso, não uma licença open source aprovada pela OSI. Para uso comercial ou permissões adicionais, entre em contato com o autor. Este documento é uma proposta de termos para o projeto, não substitui orientação jurídica.

---

<div align="center">

**Desenvolvido por Victor Andrey**
[GitHub](https://github.com/vandreysouzat-code) · [LinkedIn](https://www.linkedin.com/in/vandrey/)

*Aprender · Desenvolver · Testar · Evoluir*

</div>
