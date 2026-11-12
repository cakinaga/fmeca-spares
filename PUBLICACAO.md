# Publicação com DOI no Zenodo

Roteiro para depositar a ferramenta e obter o DOI que será citado no TCC.

## 1. Antes de publicar

- [ ] Preencher o ORCID em `CITATION.cff` (linha comentada) e em `pyproject.toml`,
      se desejar.
- [x] Ajustar `repository-code` em `CITATION.cff` para a URL real do repositório.
- [ ] Conferir o nome do titular do copyright em `LICENSE`.
- [ ] Decidir a licença. O padrão aqui é MIT, usual para software acadêmico.
      Se a preferência for impedir uso comercial fechado, GPL-3.0 é a
      alternativa comum; se a intenção for licenciar também o *método* e não
      só o código, CC BY 4.0 costuma ser depositada em paralelo. Trocar exige
      alterar `LICENSE`, `CITATION.cff` e `pyproject.toml`.
- [ ] Rodar a suíte: `pytest`.
- [ ] Confirmar que `dados/` contém o formulário FMECA na versão que será
      citada no texto, e que as planilhas de demonstração estão identificadas
      como ilustrativas.

## 2. Repositório no GitHub

```bash
git init
git add .
git commit -m "Modelo de decisão de estoque de spare parts: FMECA e lead time"
git branch -M main
git remote add origin https://github.com/cakinaga/fmeca-spares.git
git push -u origin main
```

## 3. Ligar o Zenodo ao GitHub

1. Entrar em <https://zenodo.org> com a conta do GitHub.
2. Em **GitHub** (no menu da conta), ativar o repositório `fmeca-spares`.
3. Criar um *release* no GitHub com a tag `v0.3.0`. O Zenodo captura o release
   e emite o DOI automaticamente.

O Zenodo emite dois DOIs: um para a versão (`v0.3.0`) e um *concept DOI* que
sempre aponta para a versão mais recente. **No TCC, cite o DOI da versão**, para
que o leitor chegue exatamente ao código descrito no texto.

## 4. Depois de obter o DOI

- [ ] Descomentar e preencher `doi:` e `identifiers:` em `CITATION.cff`.
- [ ] Acrescentar o selo no topo do `README.md`:

      [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX)

- [ ] Fazer o commit dessas alterações. Para que o próprio depósito contenha o
      DOI, publicar em seguida um `v0.3.1` — ou aceitar que o selo apareça
      apenas da versão seguinte em diante, o que é a prática comum.

## 5. Como citar no TCC

Formato ABNT para software com DOI:

> AKINAGA, C. Y. H. **fmeca-spares: modelo de decisão para estoque de spare
> parts na Engenharia Clínica baseado em FMECA e lead time**. Versão 0.3.0.
> [S.l.]: Zenodo, 2026. DOI: 10.5281/zenodo.XXXXXXX. Disponível em:
> https://doi.org/10.5281/zenodo.XXXXXXX. Acesso em: DD mmm. AAAA.

## 6. Hospedar o app (opcional)

O Streamlit Community Cloud publica o repositório gratuitamente: conectar a
conta do GitHub em <https://share.streamlit.io>, apontar para `app.py` e
indicar `requirements.txt`. Dá um endereço estável para a banca abrir a
ferramenta sem instalar nada. O repositório é público nesse plano, o que já
será o caso após o depósito no Zenodo.
