# Empregos Brasil

Uma ferramenta moderna, de arquivo único, para consolidação e busca de vagas de emprego. O projeto consolida um painel de controle web responsivo (SPA) e 10 scrapers (nacionais e regionais de Pernambuco) rodando inteiramente em cache volátil (memória RAM) para máxima compatibilidade com sistemas imutáveis (como o Fedora Kinoite / COSMIC).

---

## 🚀 Guia Rápido (Quick Start)

Este projeto foi projetado para ser executado de forma simples e veloz com o **uv** (gerenciador de pacotes rápido da Astral).

### 1. Iniciar a Interface Gráfica (Desktop App / Webview)
Para rodar o painel em uma janela nativa local, execute:
```bash
uv run main.py
```
* **Janela Nativa**: Se o seu sistema possuir as dependências do WebKitGTK/Qt, o aplicativo abrirá diretamente em uma janela nativa local.
* **Navegador (Fallback)**: Se o ambiente não suportar janelas nativas (como containers Distrobox isolados sem display X11/Wayland), o servidor subirá e abrirá a interface automaticamente no seu navegador padrão em `http://127.0.0.1:8000`.

### 2. Rodar a Coleta via Linha de Comando (CLI)
Se desejar executar a busca diretamente pelo terminal (opcional):
```bash
uv run main.py --cli
```

---

## 🛠️ Tecnologias e Dependências

O projeto utiliza a especificação PEP 723 de metadados em linha. Ao rodar com `uv run`, as seguintes dependências são baixadas e isoladas em cache automaticamente:
* **FastAPI** & **Uvicorn** — Servidor backend de alta performance e APIs REST.
* **PyWebView** (com **PyQt6 / WebEngine**) — Motor de renderização e exibição em janela local nativa desktop.
* **BeautifulSoup4** & **LXML** — Motores de análise de páginas HTML.
* **Requests** — Cliente HTTP para coleta.

---

## 📐 Arquitetura Imutável (Zero Disk Write)

Desenvolvido sob as diretrizes do **Fedora Kinoite (Atomic/ostree)**:
* **Zero Gravação Física no Disco**: As configurações de busca e o cache de vagas são armazenados na memória RAM do interpretador Python (`CONFIG_MEM` e `VAGAS_CACHE`). Nenhuma pasta de banco de dados ou arquivos JSON são criados no seu diretório do projeto.
* **Coleta Volátil**: Ao rodar a CLI, as saídas são direcionadas ao diretório de cache do sistema `/tmp` (montado em RAMfs), sumindo automaticamente ao reiniciar a máquina.
* **Interface Responsiva**: Design moderno baseado em glassmorphism minimalista, sem emojis e totalmente compatível com layouts de smartphones e computadores.

---

## ⚙️ Plataformas Consultadas

A busca varre de forma consolidada os seguintes portais:
1. Gupy (Filtro geográfico dinâmico)
2. LinkedIn
3. Indeed
4. InfoJobs
5. InfoJobs (Geo)
6. Emprego PE
7. Comunidade PE
8. Blogspot PE (RSS)
9. Google News
10. Jobrapido
