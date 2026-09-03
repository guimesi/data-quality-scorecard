# DQ Scorecard — UI/UX Audit (branch `feature/databricks-app-migration`)

Baseado na leitura de `app.py`, `ui/_theme.py`, `utils/session/*`, `utils/ui_components.py`, todos os `ui/step_*.py`, `ui/step_06/*`, `ui/step_07/_shared.py`, `step_adoption.py`, `config/*`, `app.yaml`.

## 1. Problemas principais (ordenados por impacto)

### Hierarquia / redundância
1. **Título repetido em 3–4 níveis.** `st.title("Data Quality Scorecard")` (app.py) + brand card na sidebar "DQ Scorecard" + `.step-pill` "Step 3 · CDE Selection" + `section_header("Step 3 - CDE selection", …)`. Quatro elementos dizem a mesma coisa antes do conteúdo começar.
2. **Cabeçalhos de step em `###` (h3)** — não existe h1/h2 de página; o único h1 é o título genérico do app.
3. **Descrições longas em caption** (60–90 palavras em Step 3, One-click, ML Lab banner) explicando implementação ("The badges above and the success banner below update on the same render, one click is enough").
4. **Ações primárias concorrentes**: Step 0 mostra botão "Select" primary no card ativo *e* "Next" primary; dashboard tem "Save", "Export CSV/JSON" por DP, "Executive report", "ML Lab" no mesmo nível.

### Navegação / sidebar
5. Sidebar = 5 widgets independentes em cards (brand gradiente, stepper, dataset size, project filter, footer com descrição do produto). Nenhum se comporta como navegação; o stepper não é clicável.
6. `render_sample_mode_toggle` e `render_planview_filter` aparecem em toda tela, inclusive na home e no dashboard, onde mudá-los apaga o trabalho (`data_products = {}`) sem confirmação.
7. Rótulos do stepper ("Standard", "Custom", "DQRs") são ambíguos fora de contexto; "🧪 ML Lab (beta)" e "📊 Adoption" usam emoji como ícone.
8. Cada step reimplementa `_nav()` com `st.columns([1,1,4,1])`; Restart via popover é bom, mas o botão tem o mesmo peso visual de Back.
9. "Usage & audit" é um botão solto abaixo de um `---` na home — parece parte do fluxo.

### Fluxo do wizard
10. Todos os DPs são renderizados **expandidos e empilhados** em Steps 3, 4, 4.2 e 5 — com 3 sistemas a página tem 3 grids de 380px + 3 blocos de regras. Não há sumário colapsado dos DPs já válidos.
11. Feedback de validação duplicado: `.cde-success` + chips no topo + chips embaixo + `st.success`; em Step 5, barra de progresso + `st.success("✅ Standard sum = 100% (OK)")`. Em Step 4.2 o erro de CDE faltante aparece no card **e** num `st.error` agregado no rodapé.
12. Textos "preservados por paridade" que hoje só duplicam: `st.markdown("**⬇ Export**")` após `.export-title`; `st.markdown(f"**Status:** {label}")` após a pill de status; `st.markdown("**Source weights…**")` após `.src-summary`; caption duplicada do "Worst rows".

### One-click
13. Domínio e sistemas usam o mesmo card de 8em min-height do step-by-step (reduzido para 4.2em); o que será automatizado só aparece num parágrafo de 40 palavras acima do botão.
14. Botão "Generate" fica numa coluna [1,2,2] à direita sem relação com o resumo; estado de execução é um único `st.spinner` com frase longa — a operação tem 6 fases reais.
15. Sistemas sem custom rules podem ser selecionados e só depois geram warning.

### Dashboard
16. Ordem narrativa invertida: banner One-click → overview → **Save project / Executive report** → cards por DP (gauge 240px + 4 metrics + barra 140px + 6 tabs) empilhados. Com 3 DPs, ~3 telas de scroll antes de ver o pior DP.
17. **Gauge** Plotly ocupa 1/3 da largura para mostrar um número que a pill já mostra. Distribuição de linhas aparece duas vezes (4 `st.metric` + barra empilhada com os mesmos números).
18. Não existe visão "onde está o problema": o usuário precisa abrir a tab Rules de cada DP e ordenar mentalmente.
19. Labels de status "🟢 Green / 🟡 Yellow / 🔴 Red" nomeiam a cor, não o significado; a cor é o único indicador nas barras Plotly.
20. Exports por DP dentro do card (2 botões × N DPs) + report executivo separado — 7 botões de download para 3 DPs.

### Cores / consistência
21. Três temas concorrentes: indigo (global), amber (One-click repinta `.step-pill`/`.sel-chip`), violeta (ML Lab repinta **todos** os containers e metrics via `!important`). Azul `#3b82f6` aparece em filter-banner, charts de history e adoption sem pertencer a nenhuma família.
22. Vermelho usado para "Blocking" (tag de regra), score baixo, botão de erro e drop alert — mesmo hue, semânticas diferentes.
23. Accent por sistema (`#3b82f6/#8b5cf6/#0ea5e9`) duplicado em 5 módulos (`step_03`, `step_04*`, `step_05`, `step_06/_shared`, `step_07/_shared`) além de `config/domains.py`.

### Cards
24. Taxonomia inflada: `card-*`, `dp-card-*`, `dp-card-title-row`, `score-card`, `src-summary`, `src-mini`, `cde-header`, `sel-summary`, `filter-banner`, `empty-notice`, `empty-callout`, `cde-empty`, `cde-success`, `ui-tip`, `worst-banner`, `lab-banner`, `lab-explain`, `lab-empty` — 18 variantes de "caixa com borda e fundo levemente colorido".
25. Card dentro de container: Step 4.2 = `st.container(border)` (DP) → `st.container(border)` (regra) → `st.expander` (details) → `st.expander` (how this option works).

### Tipografia / emojis
26. Uppercase + letter-spacing em 11 classes diferentes (`.card-subtitle`, `.mode-tagline`, `.sel-summary-title`, `.filter-title`, `.src-summary-title`, `.export-title`, `.sb-section-title`, …) com tamanhos 0.72–0.82em e cores distintas.
27. Emojis como ícones em botões (⬅ ➡ 🔄 ⚡ 💾 📂 🧪 📊), em labels de tabs do ML Lab (9 emojis), em labels de métricas (👥 🚪 🧮), em colunas de grid (🎯), em status (🟢🟡🔴) e em títulos. Renderização varia por SO; no Databricks Apps (Linux) alguns caem em fontes de fallback.

### Estados / feedback
28. Operações longas usam `st.spinner` com frases compostas; nenhuma usa `st.status` com fases. Load de projeto salvo, One-click e Step 2 têm 3–6 fases reais cada.
29. Estados vazios são `st.error("🚫 …Go back to step 2")` — erro para situação normal de navegação.
30. Sucesso é comunicado em texto longo (One-click summary de 30+ palavras em `st.success`).

### Acessibilidade
31. Status só por cor nas barras/gauge/heatmap; `rgba(49,51,63,0.55)` em 0.78em (≈ 3.4:1) em vários rótulos; `.pct-label`, `.domain-systems`, `.cde-sample` abaixo de 12px efetivos.
32. Cards "selecionáveis" não são focáveis — o controle real é o checkbox/botão abaixo; o clique no card não seleciona.

### CSS
33. `_theme.py` tem ~600 linhas com 8 gradientes, `!important` em containers/expanders/metrics, e seletores `data-testid` (5) que podem quebrar entre versões. ML Lab sobrescreve `stVerticalBlockBorderWrapper` global com `!important` para todos os containers da página.
34. Sem `.streamlit/config.toml`: o tema base é o default Streamlit (vermelho `#FF4B4B` como primary — visível em foco de inputs, sliders, toggles, checkboxes) enquanto o CSS custom usa indigo. Duas cores primárias na mesma tela.

## 2. O que está bem e deve ser preservado
- Visibilidade condicional de steps (`STEP_VISIBILITY_PREDICATES`) e o "Step X of N" honesto.
- `render_choice_card` / `render_nav_footer` como ponto único de chrome.
- `utils/colors.py` como fonte única das cores de status.
- Drill-down clique-na-barra → linhas falhas (`_drilldown.py`) — é a melhor feature do dashboard e hoje está escondida.
- Restart com confirmação; `set_domain` / `set_app_mode` idempotentes.
- Contrato de estabilidade do `data_editor` em Step 3 (bem documentado).
