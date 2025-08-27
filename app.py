# Senado Monitor — MVP
# Interface: Streamlit
# Objetivo: consultar os webservices de Dados Abertos do Senado e montar uma lista de acompanhamento
# Autor: ChatGPT (para você)
#
# Requisitos:
#   pip install streamlit requests xmltodict pandas
# Execução:
#   streamlit run app.py
#
# Observações importantes:
# - O serviço usa a rota base "https://legis.senado.leg.br/dadosabertos" (atenção: "materia" no singular)
# - Endpoints utilizados neste MVP:
#     • /materia/pesquisa/lista           — pesquisa básica por filtros simples (sigla, ano, etc.)
#     • /materia/situacaoatual/{codigo}   — situação atual de uma matéria específica
#     • /materia/atualizadas              — últimas matérias atualizadas (para checagem rápida)
# - As respostas costumam vir em XML; usamos xmltodict para transformar em dict
# - O MVP salva a carteira de acompanhamento em um arquivo JSON local (watchlist.json)

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests
import xmltodict
import pandas as pd
import streamlit as st

BASE = "https://legis.senado.leg.br/dadosabertos"
WATCHFILE = Path("watchlist.json")

# ------------------------------- Utilitários -------------------------------

def _clean_text(x: Optional[str]) -> str:
    if x is None:
        return ""
    if isinstance(x, (int, float)):
        return str(x)
    return str(x).strip()


def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Faz GET e retorna dict (a partir do XML). Trata erros de rede e XML vazio."""
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        # Respostas vêm como XML; convertemos para dict
        data = xmltodict.parse(r.text)
        return data
    except Exception as e:
        st.error(f"Erro ao acessar {url}: {e}")
        return None


# ------------------------------- Camada de dados (API) -------------------------------

def pesquisar_materias(sigla: Optional[str] = None,
                        ano: Optional[int] = None,
                        palavra_chave: Optional[str] = None,
                        codigo_situacao: Optional[str] = None,
                        tramitando: Optional[bool] = None,
                        indicador_situacao_atual: Optional[str] = None) -> pd.DataFrame:
    """Consulta /materia/pesquisa/lista.
    Parâmetros reconhecidos pelo serviço (os mais comuns):
      - sigla (ex.: PL, PEC, PLS, PLC)
      - ano (ex.: 2025)
      - palavraChave (texto livre na ementa/assuntos)
      - codigoSituacao (numérico)
      - tramitando (S/N)
      - indicadorSituacaoAtual (S/N)
    """
    url = f"{BASE}/materia/pesquisa/lista"

    params: Dict[str, Any] = {}
    if sigla:
        params["sigla"] = sigla
    if ano:
        params["ano"] = int(ano)
    if palavra_chave:
        # A API costuma usar 'palavraChave' (camelCase)
        params["palavraChave"] = palavra_chave
    if codigo_situacao:
        params["codigoSituacao"] = codigo_situacao
    if tramitando is not None:
        params["tramitando"] = "S" if tramitando else "N"
    if indicador_situacao_atual:
        params["indicadorSituacaoAtual"] = indicador_situacao_atual

    doc = _get(url, params)
    if not doc:
        return pd.DataFrame()

    # A raiz típica: PesquisaBasicaMateria > Materias > Materia (lista)
    raiz = doc.get("PesquisaBasicaMateria") or doc.get("PesquisaBasicaMateriav7") or doc
    materias = (((raiz or {}).get("Materias") or {}).get("Materia"))

    if materias is None:
        return pd.DataFrame()
    if isinstance(materias, dict):
        materias = [materias]

    # Mapeia campos úteis (nem todos vêm sempre)
    rows = []
    for m in materias:
        rows.append({
            "codigo": _clean_text(m.get("Codigo")),
            "sigla": _clean_text(m.get("Sigla")),
            "numero": _clean_text(m.get("Numero")),
            "ano": _clean_text(m.get("Ano")),
            "ementa": _clean_text(m.get("Ementa")),
            "autor": _clean_text(m.get("Autor")),
            "situacao": _clean_text(((m.get("SituacaoAtual") or {}).get("DescricaoSituacao"))),
            "link_tramitacao": _clean_text(((m.get("LinkProcesso") or m.get("UrlTramitacao") or ""))),
        })

    df = pd.DataFrame(rows)
    # Colunas em ordem amigável
    cols = ["codigo", "sigla", "numero", "ano", "ementa", "autor", "situacao", "link_tramitacao"]
    df = df.reindex(columns=cols)
    return df


def situacao_atual(codigo: str) -> Dict[str, Any]:
    """Consulta /materia/situacaoatual/{codigo} e retorna dados essenciais."""
    url = f"{BASE}/materia/situacaoatual/{codigo}"
    doc = _get(url)
    if not doc:
        return {}
    raiz = doc.get("SituacaoAtualMateria") or doc
    materia = ((raiz.get("Materia") or {}))
    sit = ((raiz.get("SituacaoAtual") or {}))
    return {
        "codigo": _clean_text(materia.get("Codigo")) or _clean_text(codigo),
        "descricao": _clean_text(sit.get("DescricaoSituacao")),
        "data": _clean_text(sit.get("DataSituacao")),
        "orgao": _clean_text(sit.get("DescricaoOrgao")),
    }


def materias_atualizadas() -> pd.DataFrame:
    """Consulta /materia/atualizadas e retorna um DF com códigos e textos básicos.
       Útil para ver o que mudou recentemente.
    """
    url = f"{BASE}/materia/atualizadas"
    doc = _get(url)
    if not doc:
        return pd.DataFrame()

    raiz = doc.get("AtualizacoesMateria") or doc
    itens = ((raiz.get("Materias") or {}).get("Materia"))
    if itens is None:
        return pd.DataFrame()
    if isinstance(itens, dict):
        itens = [itens]

    rows = []
    for m in itens:
        rows.append({
            "codigo": _clean_text(m.get("Codigo")),
            "sigla": _clean_text(m.get("Sigla")),
            "numero": _clean_text(m.get("Numero")),
            "ano": _clean_text(m.get("Ano")),
            "ultima_atualizacao": _clean_text(m.get("DataUltimaAtualizacao") or m.get("DataAtualizacao")),
            "ementa": _clean_text(m.get("Ementa")),
        })
    return pd.DataFrame(rows)


# ------------------------------- Persistência simples (carteira) -------------------------------

def load_watchlist() -> Dict[str, Any]:
    if WATCHFILE.exists():
        try:
            return json.loads(WATCHFILE.read_text(encoding="utf-8"))
        except Exception:
            return {"itens": {}, "historico": []}
    return {"itens": {}, "historico": []}
