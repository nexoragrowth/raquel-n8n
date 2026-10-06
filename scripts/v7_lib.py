# -*- coding: utf-8 -*-
"""v7_lib.py — helpers para GENERAR los workflows del v7 como JSON de n8n (nodos, conexiones, credenciales). Sin red.
El codigo de los nodos Code sale de los archivos de v7/*.js (una sola fuente de verdad, probada offline)."""
import json, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V7 = ROOT / "v7"
CRED_REDIS = {"redis": {"id": "kdtSKwGbN1xAZeUh", "name": "Redis account"}}
CRED_DENTALINK = {"httpHeaderAuth": {"id": "TwN6eBWsydjMdsCM", "name": "Header Auth account 3"}}
CRED_POSTGRES = {"postgres": {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}}
CRED_OPENAI = {"openAiApi": {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}}
DENTALINK = "https://api.dentalink.healthatom.com/api/v1"
SETTINGS = {"executionOrder": "v1", "callerPolicy": "workflowsFromSameOwner", "availableInMCP": False, "binaryMode": "separate", "errorWorkflow": "yop6TIVoKiWUxfEn"}


def core(nombre):
    """Fuente de un modulo v7/<nombre>.js (se antepone al codigo del nodo)."""
    return (V7 / f"{nombre}.js").read_text(encoding="utf-8").rstrip() + "\n"


class Grafo:
    def __init__(self, nombre):
        self.nombre = nombre
        self.nodos = []
        self.con = {}
        self._x = 0

    def _nodo(self, nombre, tipo, version, params, x, y, extra=None):
        n = {"parameters": params, "id": str(uuid.uuid4()), "name": nombre, "type": tipo, "typeVersion": version, "position": [x, y]}
        n.update(extra or {})
        if any(m["name"] == nombre for m in self.nodos):
            raise ValueError("nodo duplicado: " + nombre)
        self.nodos.append(n)
        return nombre

    def trigger(self, ejemplo, x=0, y=0, nombre="Entrada"):
        return self._nodo(nombre, "n8n-nodes-base.executeWorkflowTrigger", 1.1, {"inputSource": "jsonExample", "jsonExample": json.dumps(ejemplo, ensure_ascii=False)}, x, y)

    def code(self, nombre, js, x=0, y=0, usar=()):
        pre = "".join(core(m) for m in usar)
        return self._nodo(nombre, "n8n-nodes-base.code", 2, {"jsCode": pre + js}, x, y)

    def si(self, nombre, expr_bool, x=0, y=0):
        """IF v2.2: salida 0 = verdadero, salida 1 = falso."""
        cond = {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [{"id": str(uuid.uuid4()), "leftValue": "={{ " + expr_bool + " }}", "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                "combinator": "and"}
        return self._nodo(nombre, "n8n-nodes-base.if", 2.2, {"conditions": cond, "options": {}}, x, y)

    def redis_get(self, nombre, key_expr, propiedad, x=0, y=0):
        return self._nodo(nombre, "n8n-nodes-base.redis", 1, {"operation": "get", "propertyName": propiedad, "key": "={{ " + key_expr + " }}", "keyType": "string", "options": {}}, x, y,
                          {"credentials": CRED_REDIS, "alwaysOutputData": True, "onError": "continueRegularOutput"})

    def redis_set(self, nombre, key_expr, value_expr, ttl, x=0, y=0):
        return self._nodo(nombre, "n8n-nodes-base.redis", 1, {"operation": "set", "key": "={{ " + key_expr + " }}", "value": "={{ " + value_expr + " }}", "keyType": "string", "expire": True, "ttl": ttl}, x, y,
                          {"credentials": CRED_REDIS, "onError": "continueRegularOutput"})

    def redis_incr(self, nombre, key_expr, ttl, x=0, y=0):
        return self._nodo(nombre, "n8n-nodes-base.redis", 1, {"operation": "incr", "key": "={{ " + key_expr + " }}", "expire": True, "ttl": ttl}, x, y,
                          {"credentials": CRED_REDIS, "alwaysOutputData": True, "onError": "continueRegularOutput"})

    def dentalink(self, nombre, metodo, url_expr, body_expr=None, x=0, y=0, query_expr=None):
        p = {"method": metodo, "url": "={{ " + url_expr + " }}", "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth", "options": {"timeout": 8000}}
        if query_expr:
            p.update({"sendQuery": True, "queryParameters": {"parameters": [{"name": "q", "value": "={{ " + query_expr + " }}"}]}})
        if body_expr:
            p.update({"sendBody": True, "specifyBody": "json", "jsonBody": "={{ " + body_expr + " }}"})
        return self._nodo(nombre, "n8n-nodes-base.httpRequest", 4.2, p, x, y, {"credentials": CRED_DENTALINK, "alwaysOutputData": True, "continueOnFail": True})

    def subworkflow(self, nombre, workflow_id, entradas, x=0, y=0):
        """Execute Workflow v1.2 con entradas definidas (expresiones n8n sin el '={{ }}')."""
        valores = {k: "={{ " + v + " }}" for k, v in entradas.items()}
        return self._nodo(nombre, "n8n-nodes-base.executeWorkflow", 1.2, {"workflowId": {"__rl": True, "value": workflow_id, "mode": "id"},
                          "workflowInputs": {"mappingMode": "defineBelow", "value": valores, "matchingColumns": [], "schema": []}, "options": {}}, x, y,
                          {"alwaysOutputData": True, "continueOnFail": True})

    def redis_del(self, nombre, key_expr, x=0, y=0):
        return self._nodo(nombre, "n8n-nodes-base.redis", 1, {"operation": "delete", "key": "={{ " + key_expr + " }}"}, x, y, {"credentials": CRED_REDIS, "onError": "continueRegularOutput"})

    def postgres(self, nombre, query, params_expr, x=0, y=0):
        """Consulta Postgres (Supabase v3). params_expr = expresión n8n que devuelve el texto o el ARRAY de parámetros ($1, $2…)."""
        return self._nodo(nombre, "n8n-nodes-base.postgres", 2.5, {"operation": "executeQuery", "query": query, "options": {"queryReplacement": "={{ " + params_expr + " }}"}}, x, y,
                          {"credentials": CRED_POSTGRES, "alwaysOutputData": True, "continueOnFail": True})

    def agente(self, nombre, texto_expr, sistema_expr, x=0, y=0, max_iter=5):
        """AI Agent (Tools Agent) v2.2. El mensaje y el system prompt entran por expresión."""
        return self._nodo(nombre, "@n8n/n8n-nodes-langchain.agent", 2.2,
                          {"promptType": "define", "text": "={{ " + texto_expr + " }}", "options": {"systemMessage": "={{ " + sistema_expr + " }}", "maxIterations": max_iter, "returnIntermediateSteps": True}}, x, y,
                          {"onError": "continueRegularOutput"})

    def modelo(self, nombre, modelo="gpt-5-mini", esfuerzo="low", x=0, y=0):
        return self._nodo(nombre, "@n8n/n8n-nodes-langchain.lmChatOpenAi", 1.2,
                          {"model": {"__rl": True, "value": modelo, "mode": "list", "cachedResultName": modelo}, "options": {"reasoningEffort": esfuerzo}}, x, y, {"credentials": CRED_OPENAI})

    def herramienta(self, nombre, descripcion, workflow_id, fijos, del_modelo, x=0, y=0):
        """Tool Workflow v2.2. `fijos` = {campo: expresión} que NUNCA decide el modelo (teléfono, ejecución, modo); `del_modelo` = {campo: descripción} con $fromAI."""
        valores, esquema = {}, []
        for k, expr in fijos.items():
            valores[k] = "={{ " + expr + " }}"
            esquema.append({"id": k, "displayName": k, "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string"})
        for k, desc in del_modelo.items():
            valores[k] = "={{ $fromAI('" + k + "', " + json.dumps(desc, ensure_ascii=False) + ", 'string', '') }}"
            esquema.append({"id": k, "displayName": k, "required": False, "defaultMatch": False, "display": True, "canBeUsedToMatch": True, "type": "string"})
        p = {"description": descripcion, "workflowId": {"__rl": True, "value": workflow_id, "mode": "id"},
             "workflowInputs": {"mappingMode": "defineBelow", "value": valores, "matchingColumns": [], "schema": esquema, "attemptToConvertTypes": False, "convertFieldsToString": True}}
        return self._nodo(nombre, "@n8n/n8n-nodes-langchain.toolWorkflow", 2.2, p, x, y)

    def conectar_ai(self, de, a, tipo):
        """Conexión de IA (ai_tool / ai_languageModel / ai_memory): el nodo `de` alimenta al agente `a`."""
        self.con.setdefault(de, {}).setdefault(tipo, [[]])[0].append({"node": a, "type": tipo, "index": 0})

    def conectar(self, de, a, salida=0):
        self.con.setdefault(de, {"main": []})["main"]
        ramas = self.con[de]["main"]
        while len(ramas) <= salida:
            ramas.append([])
        ramas[salida].append({"node": a, "type": "main", "index": 0})

    def json(self):
        return {"name": self.nombre, "nodes": self.nodos, "connections": self.con, "settings": dict(SETTINGS), "staticData": None}
