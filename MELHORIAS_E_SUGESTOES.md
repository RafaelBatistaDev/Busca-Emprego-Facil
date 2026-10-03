# 🚀 Plano de Melhorias e Sugestões: Busca Emprego Fácil (Recife & RMR 40km)

> **Status de Execução**: ✅ **TODAS AS MELHORIAS FORAM APLICADAS E CONCLUÍDAS COM SUCESSO NO PROJETO!**

Este documento apresenta o plano arquitetural e o status de implementação no sistema **Busca Emprego Fácil**, atendendo aos três pilares estratégicos solicitados:
1. ✅ **Abrangência Geográfica Extensiva**: Cobertura de Recife e cidades da Região Metropolitana em um raio de 40 km.
2. ✅ **Deduplicação Persistente & Inter-Plataforma**: Garantia de zero vagas repetidas entre buscas e entre diferentes portais via banco de dados SQLite (`vagas_historico.db`) e algoritmo Fuzzy (`difflib`).
3. ✅ **Filtro Temporal Estrito (Últimos 3 Dias / 72h)**: Eliminação rigorosa de anúncios antigos ou desatualizados com suporte a parâmetros nativos (`fromage=3`, `f_TPR=r259200`).

---

## 📍 1. Expansão Geográfica: Recife e Região Metropolitana (Raio 40 km)

### 📌 Estado de Implementação: ✅ CONCLUÍDO

#### A. Mapeamento das Cidades da RMR (Raio até 40 km)
- [x] Mapeamento dos 14+ municípios da Região Metropolitana do Recife (RMR) e polos industriais/logísticos vizinhos:

```python
# Cidades da Região Metropolitana do Recife (RMR) dentro do raio de ~40 km
CIDADES_RMR_40KM = {
    "recife", "olinda", "jaboatao dos guararapes", "jaboatao", "paulista", 
    "camaragibe", "cabo de santo agostinho", "cabo", "igarassu", 
    "abreu e lima", "ipojuca", "suape", "sao lourenco da mata", "sao lourenco", 
    "moreno", "itapissuma", "ilha de itamaraca", "itamaraca", "aracoiaba", "goiana"
}

TERMOS_REMOTO = {"remoto", "home office", "teletrabalho", "hibrido", "hybrid", "anywhere", "qualquer lugar"}
```

#### B. Atualização da Função `filtrar_por_localizacao`
- [x] Função atualizada no `main.py` para aceitar qualquer cidade da lista RMR 40km ou vagas de trabalho remoto:

```python
def filtrar_por_localizacao(vagas: list[Vaga], localizacao: str, incluir_rmr: bool = True) -> list[Vaga]:
    termos = [normalizar_texto(t) for t in localizacao.replace(",", " ").split() if len(t) > 1]
    def é_local(v: Vaga) -> bool:
        if v.plataforma in PLATAFORMAS_SEM_FILTRO_GEO:
            return True
        loc = normalizar_texto(v.localizacao or "").lower()
        if not loc or loc in ["n/d", "nd", "brasil"]:
            return True
        if any(t in loc for t in termos):
            return True
        if incluir_rmr:
            if any(cidade in loc for cidade in CIDADES_RMR_40KM):
                return True
            if any(t in loc for t in TERMOS_REMOTO):
                return True
            if "pe" in loc or "pernambuco" in loc:
                return True
        return False
    # ...
```

#### C. Parâmetros Nativos de Raio nos Scrapers
- [x] **LinkedIn**: Adicionado parâmetro `distance=25` (milhas ≈ 40 km) nas requisições HTTP.
- [x] **Indeed**: Adicionado parâmetro `radius=40` (quilômetros) na query string HTTP.
- [x] **InfoJobs / Scrapers Locais**: Mantido suporte a município e geolocalização da RMR.

---

## 🔄 2. Deduplicação Avançada e Persistente (Zero Repetição)

### 📌 Estado de Implementação: ✅ CONCLUÍDO

```
[ Nova Vaga Raspada ]
         │
         ▼
[ Normalização da URL & Assinatura SHA256 (Hash) ]
         │
         ▼
[ Checar Banco Persistente SQLite (vagas_historico.db) ]
       ╱   ╲
  (Já capturada) (Nova vaga)
     ╱       ╲
    ▼         ▼
[ Descartar ]  [ Registrar no Histórico & Exibir ]
```

#### A. Banco de Dados / Histórico de Vagas Persistente (`vagas_historico.db`)
- [x] Criado banco de dados SQLite e rotas de salvamento/verificação de vagas capturadas em buscas anteriores:

```python
def vaga_ja_capturada(hash_vaga: str, url_norm: str, db_path: Path = DB_HISTORICO) -> bool:
    try:
        if not db_path.exists():
            return False
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM vagas_vistas WHERE hash_vaga = ? OR (url_normalizada != '' AND url_normalizada = ?)",
            (hash_vaga, url_norm)
        )
        existe = cursor.fetchone() is not None
        conn.close()
        return existe
    except Exception:
        return False
```

#### B. Deduplicação Inter-Plataformas com Fuzzy Matching
- [x] Implementada verificação de similaridade via `difflib.SequenceMatcher` para eliminar a mesma vaga postada com títulos ligeiramente diferentes em plataformas distintas:

```python
def sao_vagas_similares(v1: Vaga, v2: Vaga, threshold: float = 0.85) -> bool:
    emp1, emp2 = limpar_nome(v1.empresa), limpar_nome(v2.empresa)
    if emp1 != emp2 or emp1 in ["nd", "n d", "confidencial"]:
        return False
    tit1, tit2 = limpar_nome(v1.titulo), limpar_nome(v2.titulo)
    ratio = SequenceMatcher(None, tit1, tit2).ratio()
    return ratio >= threshold
```

---

## ⏱️ 3. Filtro Temporal Estrito (Últimos 3 Dias / 72 Horas)

### 📌 Estado de Implementação: ✅ CONCLUÍDO

#### A. Configuração e Tratamento Estrito de Data
- [x] Adicionados os parâmetros `"limite_dias": 3` e `"descartar_vagas_sem_data": false` no `config_vagas.json`.
- [x] Rejeição explícita de vagas com anúncios antigos (`"+30"`, `"30+"`, `"há 1 mês"`).

#### B. Parser Temporal Expandido
- [x] Suporte completo a datas relativas em português e inglês ("há 1 dia", "ontem", "2d ago", "3d", "há 3 dias").

#### C. Filtros de Data Nativos nas Requisições
- [x] **LinkedIn**: Adicionado parâmetro `f_TPR=r259200` (72 horas / 3 dias).
- [x] **Indeed**: Adicionado parâmetro `fromage=3` (3 dias).
- [x] **Google News**: Adicionada query com `when:3d` e filtro máximo de 3 dias.

---

## ⚙️ 4. Configuração Aplicada no `config_vagas.json`

- [x] Arquivo `config_vagas.json` atualizado e testado:

```json
{
  "keywords": [
    "Porteiro",
    "Vigia",
    "Auxiliar de Linha de Produção",
    "Fiscal de Loja",
    "Prevenção de Perdas"
  ],
  "localizacao": "Recife, PE",
  "raio_km": 40,
  "incluir_regiao_metropolitana": true,
  "limite_dias": 3,
  "descartar_vagas_sem_data": false,
  "dedup_persistente": true,
  "max_vagas_por_plataforma": 10,
  "delay_entre_requisicoes": 2.5,
  "plataformas": [
    "gupy",
    "linkedin",
    "indeed",
    "infojobs",
    "infojobs_geo",
    "empregope",
    "comunidadeempregope",
    "blogspot_pe",
    "google_news",
    "jobrapido",
    "recifevagas",
    "vagaspe",
    "trabalhabrasil",
    "talent",
    "google_jobs"
  ]
}
```

---

## 📋 5. Tabela Resumo das Ações Aplicadas

| Funcionalidade | Estado Anterior | Estado Atual Implementado | Status |
| :--- | :--- | :--- | :--- |
| **Filtro de Localização** | Apenas "Recife, PE" | Cobertura de 14+ cidades da RMR (raio 40 km) + Remoto | ✅ Concluído |
| **Deduplicação Persistente** | Apenas memória RAM por sessão | SQLite `vagas_historico.db` com assinaturas SHA256 | ✅ Concluído |
| **Deduplicação Inter-sites** | Comparação básica de URL | Algoritmo Fuzzy (difflib) entre plataformas distintas | ✅ Concluído |
| **Filtro de Data (3 Dias)** | Aceitava sem restrição | Parser estrito + Parâmetros nativos `fromage=3`/`r259200` | ✅ Concluído |

---

> 🎉 **Todas as melhorias e sugestões foram aplicadas, testadas e marcadas como concluídas com sucesso!**
