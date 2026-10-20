# -*- coding: utf-8 -*-
"""Camada de auditoria: hash do documento, versões, log de execução e
reprodutibilidade. Tudo que o relatório mostra sai daqui."""
import hashlib, json, platform, sys
from datetime import datetime, timezone

import extratores, motor, ia
from checklist_parecer_tecnico import VERSAO_REGRAS


def sha256_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()


def executar_verificacao(caminho, origem=None):
    """Roda o motor uma vez e devolve o registro auditável completo."""
    log = []
    inicio = datetime.now(timezone.utc)
    log.append(f"{inicio.isoformat()} início da verificação de '{caminho}'")
    sha = sha256_arquivo(caminho)
    log.append(f"sha256 do documento: {sha}")
    doc = extratores.extrair(caminho)
    log.append(f"extração: formato={doc.formato}, páginas/abas={doc.num_paginas}")
    t0 = datetime.now(timezone.utc)
    ia.reset_contadores()
    resultados = motor.verificar(doc)
    t1 = datetime.now(timezone.utc)
    log.append(f"motor {motor.MOTOR_VERSAO}: {len(resultados)} itens avaliados em {(t1-t0).total_seconds():.3f}s")
    analise_ia = ia.comentar(resultados) if ia.disponivel() else None
    log.append("análise auxiliar de IA (resumo + comentários): " + ("gerada" if analise_ia else "indisponível"))
    ia_status = ia.status()
    if ia_status["falhas"]:
        log.append(f"ATENÇÃO: IA ({ia_status['modelo']}) falhou {ia_status['falhas']}x nesta execução ({ia_status['ultimo_erro']}); itens de classe B avaliados por heurística simulada")
    fim = datetime.now(timezone.utc)
    log.append(f"{fim.isoformat()} fim da verificação")
    registro = {
        "documento": {
            "nome": caminho.rsplit("/", 1)[-1],
            "caminho": caminho,
            "sha256": sha,
            "formato": doc.formato,
            "paginas_ou_abas": doc.num_paginas,
            "origem_url": origem,
        },
        "regras": {
            "versao": VERSAO_REGRAS,
            "motor": motor.MOTOR_VERSAO,
            "fonte_checklist": "print da planilha FRM-SEMEC-001 (slide 12 do PPTX da AP); planilha original não fornecida",
        },
        "ia": ia_status,
        "execucao": {
            "inicio_utc": inicio.isoformat(),
            "fim_utc": fim.isoformat(),
            "python": sys.version.split()[0],
            "plataforma": platform.platform(),
        },
        "resultados": resultados,
        "log": log,
    }
    if analise_ia:
        registro["analise_ia"] = analise_ia
    return registro


def resumo_status(resultados):
    cont = {}
    for r in resultados:
        cont[r["status"]] = cont.get(r["status"], 0) + 1
    return cont


def _sem_relógio(registro):
    """Cópia do registro sem campos de relógio, para comparar reprodutibilidade."""
    copia = json.loads(json.dumps(registro))
    copia["execucao"]["inicio_utc"] = ""
    copia["execucao"]["fim_utc"] = ""
    copia["log"] = [l for l in copia["log"] if "início" not in l and "fim" not in l and "avaliados em" not in l]
    copia.pop("analise_ia", None)  # texto auxiliar gerado por IA: não é decisão e varia entre execuções
    return copia


def verificar_reprodutibilidade(caminho, origem=None):
    """Executa duas vezes e compara. Retorna (registro, reproduzivel)."""
    r1 = executar_verificacao(caminho, origem)
    r2 = executar_verificacao(caminho, origem)
    j1 = json.dumps(_sem_relógio(r1), ensure_ascii=False, sort_keys=True)
    j2 = json.dumps(_sem_relógio(r2), ensure_ascii=False, sort_keys=True)
    ok = hashlib.sha256(j1.encode()).hexdigest() == hashlib.sha256(j2.encode()).hexdigest()
    r1["reprodutibilidade"] = {
        "duas_execucoes_identicas": ok,
        "nota": "comparação exclui carimbos de data/hora e o bloco analise_ia (texto auxiliar gerado por IA, não participa das decisões de status)",
        "hash_do_resultado": hashlib.sha256(j1.encode()).hexdigest(),
    }
    r1["log"].append(f"reprodutibilidade: duas execuções idênticas = {ok}")
    return r1, ok
