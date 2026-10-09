# 🛡️ Cloud Security Monitor

**Monitoramento de disponibilidade, desempenho e segurança de websites com Python.**

O **Cloud Security Monitor** é um projeto de desenvolvimento voltado ao estudo e à aplicação prática de conceitos de análise e desenvolvimento de sistemas, monitoramento, redes e segurança da informação.

A aplicação utiliza Python e Flask para realizar verificações de serviços web, acompanhar indicadores de desempenho, registrar eventos e apresentar informações por meio de uma API e de um dashboard.

> 🚧 **Status:** Em desenvolvimento — projeto de estudo e evolução contínua.

---

## 🎯 Objetivo do projeto

Desenvolver uma ferramenta de monitoramento que permita acompanhar a disponibilidade de websites, identificar falhas de comunicação e organizar informações importantes para análise técnica.

O projeto também serve como ambiente de aprendizagem prática para desenvolvimento backend, integração de componentes, tratamento de erros, registros de eventos e visualização de métricas.

## ⚙️ Funcionalidades

* 🌐 **Monitoramento de URLs:** verificação da disponibilidade de serviços web.
* 📡 **Verificação HTTP:** identificação do status retornado pelo servidor.
* ⏱️ **Tempo de resposta:** acompanhamento do tempo necessário para obter uma resposta.
* 🔐 **Monitoramento SSL:** acompanhamento da validade de certificados SSL.
* 📋 **Registro de eventos:** armazenamento de informações e ocorrências em logs.
* 🚨 **Identificação de falhas:** acompanhamento de erros e falhas consecutivas.
* 📊 **Métricas de disponibilidade:** organização de indicadores para análise.
* 🔌 **API:** disponibilização de informações para consulta programática.
* 🖥️ **Dashboard web:** visualização das informações de monitoramento em uma interface centralizada.

As funcionalidades representam o escopo atual e a evolução planejada do projeto; a cobertura de cada recurso pode variar conforme a implementação em desenvolvimento.

---

## 🧰 Tecnologias utilizadas

| Tecnologia | Aplicação no projeto                |
| ---------- | ----------------------------------- |
| Python     | Lógica da aplicação e monitoramento |
| Flask      | Aplicação web e integração de rotas |
| Requests   | Requisições HTTP                    |
| SQLite     | Persistência de dados               |
| Git        | Controle de versão                  |
| GitHub     | Hospedagem do código e documentação |

---

## 📁 Estrutura do projeto

```text
cloud-security-monitor/
│
├── app.py                 # Aplicação principal
├── api.py                 # Rotas e recursos da API
├── config.py              # Configurações
├── logger.py              # Registro de eventos
├── metrics.py             # Métricas de monitoramento
├── monitor.py             # Lógica de monitoramento
├── security.py            # Componentes relacionados à segurança
│
├── templates/
│   └── dashboard.html     # Interface do dashboard
│
├── logs/                  # Diretório de registros
├── .gitignore
└── README.md
```

---

## 🚀 Como executar

### 1. Pré-requisitos

* Python instalado.
* Git instalado.
* Terminal ou editor de código, como o Visual Studio Code.

### 2. Clone o repositório

```bash
git clone https://github.com/vandreysouzat-code/cloud-security-monitor.git
```

Entre no diretório:

```bash
cd cloud-security-monitor
```

### 3. Crie um ambiente virtual

```bash
python -m venv .venv
```

Ative o ambiente virtual no Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Instale as dependências básicas

```bash
python -m pip install flask requests
```

Se o projeto utilizar outras bibliotecas, instale também as dependências correspondentes.

### 5. Execute a aplicação

```bash
python app.py
```

Se a configuração atual iniciar o servidor na porta padrão do projeto, acesse:

```text
http://127.0.0.1:5000
```

> **Nota:** os comandos pressupõem que `app.py` inicia a aplicação Flask e que as dependências listadas são suficientes para a configuração atual. Caso o projeto tenha requisitos adicionais, consulte os imports e as configurações existentes.

---

## 🧠 Conceitos praticados

Este projeto contribui para o desenvolvimento de conhecimentos em:

* Programação com Python.
* Criação de aplicações web com Flask.
* Requisições HTTP e comunicação entre serviços.
* Tratamento de exceções e falhas.
* Organização de código em módulos.
* Registro de eventos e análise de métricas.
* Persistência de dados.
* Monitoramento e fundamentos de segurança de aplicações.
* Controle de versão com Git e GitHub.

---

## 🔭 Próximas melhorias

O projeto pode evoluir com a implementação de recursos como:

* [ ] Histórico detalhado de verificações.
* [ ] Armazenamento e visualização da evolução das métricas.
* [ ] Configuração de intervalos de monitoramento.
* [ ] Alertas para indisponibilidade de serviços.
* [ ] Relatórios exportáveis.
* [ ] Autenticação e gerenciamento de usuários.
* [ ] Aprimoramento dos testes automatizados.
* [ ] Melhorias de segurança, configuração e implantação.

---

## 👨‍💻 Autor

**Victor Andrey**

Estudante de **Análise e Desenvolvimento de Sistemas (ADS)**, desenvolvendo projetos práticos para aprofundar conhecimentos em Python, desenvolvimento de sistemas, redes e cibersegurança.

* GitHub: [@vandreysouzat-code](https://github.com/vandreysouzat-code)
* Projeto: [Cloud Security Monitor](https://github.com/vandreysouzat-code/cloud-security-monitor)

---

<div align="center">

**Aprender · Desenvolver · Testar · Evoluir**

*Projeto desenvolvido para fins de estudo e aprimoramento técnico.*

</div>
