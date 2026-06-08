# Busca Emprego Fácil

Uma ferramenta moderna, profissional e de arquivo único para consolidação e busca de vagas de emprego. O projeto une um painel de controle web responsivo (SPA) e 10 scrapers (nacionais e regionais de Pernambuco) rodando inteiramente em cache volátil (memória RAM) para máxima compatibilidade com sistemas imutáveis (como o Fedora Kinoite / COSMIC).

A janela nativa abre com dimensões otimizadas de 1000x700 pixels e o aplicativo configura automaticamente seu próprio ícone e atalho no seu lançador de aplicativos Linux.

---

## 🚀 Como Usar pela Primeira Vez (Instalação e Execução)

O projeto foi projetado para ser gerenciado de forma simples e rápida com o **uv** (gerenciador de ambientes virtuais ultrarrápido do ecossistema Python).

### Método 1: Inicialização via Terminal (Primeiro Uso)
Abra a pasta do projeto no seu terminal e execute:
```bash
uv run main.py
```
> [!NOTE]
> Ao iniciar o aplicativo via terminal, a rotina interna irá copiar e configurar automaticamente os arquivos `buscaempregofacil.desktop` e `buscaempregofacil.png` no seu diretório `~/.local/share/`.

### Método 2: Execução Direta pelo Lançador do Sistema (Dock/Menu)
Depois de rodar o aplicativo pela primeira vez (Método 1), você não precisará mais abrir o terminal para usá-lo:
1. Abra o menu de aplicativos do seu sistema operacional (KDE Application Menu, GNOME Activities, COSMIC App Grid, etc.).
2. Procure por **Busca Emprego Fácil**.
3. Clique no atalho para carregar o aplicativo de vagas diretamente em sua janela dedicada do WebView.

---

## 🌟 Funcionalidades Principais

* **Instalação Automática de Atalho (`.desktop`)**: Ao executar o aplicativo pela primeira vez, ele instala automaticamente o atalho de sistema em `~/.local/share/applications/` e o ícone em `~/.local/share/icons/`.
* **Integração no Dock/Painel**: Associação transparente entre a janela nativa do WebView (`PyQt6`) e o atalho do sistema via mapeamento de `StartupWMClass`. O ícone do aplicativo aparecerá corretamente na sua barra de tarefas/dock do sistema operacional.
* **Zero Gravação em Disco (Zero Disk Write)**: Configurações de busca e cache de vagas são mantidos inteiramente em memória RAM, em total conformidade com sistemas operacionais atômicos/imutáveis.
* **Layout Responsivo SPA**: Painel de controle moderno em estilo glassmorphism, livre de emojis, projetado para se adaptar perfeitamente a computadores e telas móveis.
* **Controle de Cache HTTP**: Cabeçalhos contra armazenamento de cache aplicados na raiz do servidor para garantir que o frontend carregue sempre a versão mais atualizada.

---

## ⚙️ Parâmetros CLI Avançados

Se preferir utilizar a ferramenta através de automações ou diretamente no terminal, utilize os parâmetros integrados de linha de comando:

* **Exibir o menu de ajuda**:
  ```bash
  uv run main.py --help
  ```
* **Executar a busca e salvar o JSON de forma direta (Modo CLI)**:
  ```bash
  uv run main.py --cli
  ```
  *As saídas serão salvas no diretório `/tmp` do sistema operacional.*
* **Alterar a porta do servidor local**:
  ```bash
  uv run main.py --port 8999
  ```

---

## 🛠️ Tecnologias e Dependências

O projeto utiliza a especificação PEP 723 de metadados inline no Python. Ao executar com `uv run`, todas as dependências são obtidas e isoladas automaticamente:
* **FastAPI** & **Uvicorn** — Servidor backend assíncrono e APIs REST.
* **PyWebView** (com **PyQt6 / WebEngine**) — Janela nativa local e mecanismo de renderização Web.
* **BeautifulSoup4** & **LXML** — Biblioteca de raspagem de dados de portais HTML.
* **Requests** — Cliente para requisições HTTP rápidas.

---

## 📐 Plataformas Integradas (Scrapers)

O mecanismo varre e unifica as vagas encontradas nos seguintes portais:
1. Gupy (Filtro geográfico em tempo real)
2. LinkedIn
3. Indeed
4. InfoJobs
5. InfoJobs (Geo)
6. Emprego PE
7. Comunidade PE
8. Blogspot PE (Feed RSS)
9. Google News
10. Jobrapido

---

## 🔧 Solução de Problemas (Falta de Dependências de Sistema)

Se o aplicativo exibir o aviso `[Aviso] Não foi possível abrir a janela nativa local` no terminal e abrir o navegador padrão do sistema em vez da janela local, significa que o seu sistema operacional não possui as bibliotecas gráficas do motor C++ Qt6-WebEngine instaladas no host.

Para resolver e habilitar a janela desktop nativa, execute o comando correspondente à sua distribuição Linux:

* **Fedora / Red Hat (RHEL)**:
  ```bash
  sudo dnf install qt6-qtwebengine
  ```
  *(Se você utiliza um sistema atômico como o **Fedora Kinoite / Silverblue**, instale no host usando `rpm-ostree install qt6-qtwebengine` e reinicie a máquina, ou utilize dentro de uma Distrobox configurada).*

* **Ubuntu / Debian / Linux Mint**:
  ```bash
  sudo apt update && sudo apt install libqt6webenginecore6
  ```

* **Arch Linux / Manjaro**:
  ```bash
  sudo pacman -S qt6-webengine
  ```

> [!TIP]
> Caso você não deseje instalar essas dependências no sistema, o aplicativo **continuará funcionando perfeitamente** através do modo de fallback automático, que cria o servidor e inicia a interface de forma transparente diretamente no seu navegador padrão.
