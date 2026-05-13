// Lee un workflow n8n de stdin, calcula layout con dagre y emite JSON
// con { positions: { nodeName: [x, y] }, stickyBoxes: { stickyName: {x,y,w,h} } }
//
// Dagre params optimizados para n8n:
//   rankdir LR (left to right)
//   nodesep horizontal entre filas paralelas
//   ranksep horizontal entre columnas (depth)
//   AI children: se manejan como un cluster aparte, posicionados debajo del padre

const dagre = require("dagre");

let raw = "";
process.stdin.on("data", (chunk) => (raw += chunk));
process.stdin.on("end", () => {
  const wf = JSON.parse(raw);
  const nodes = wf.nodes;
  const connections = wf.connections;

  const AI_CHILD_TYPES = new Set([
    "@n8n/n8n-nodes-langchain.lmChatOpenAi",
    "@n8n/n8n-nodes-langchain.lmChatGroq",
    "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "@n8n/n8n-nodes-langchain.memoryPostgresChat",
    "@n8n/n8n-nodes-langchain.memoryBufferWindow",
    "@n8n/n8n-nodes-langchain.embeddingsOpenAi",
    "@n8n/n8n-nodes-langchain.toolHttpRequest",
    "@n8n/n8n-nodes-langchain.toolCode",
    "@n8n/n8n-nodes-langchain.vectorStoreSupabase",
  ]);

  const opNodes = nodes.filter((n) => n.type !== "n8n-nodes-base.stickyNote");
  const stickies = nodes.filter((n) => n.type === "n8n-nodes-base.stickyNote");
  const opByName = Object.fromEntries(opNodes.map((n) => [n.name, n]));

  // Detectar AI children + sus padres via connections ai_*
  const aiParent = {}; // child -> parent
  for (const [src, conns] of Object.entries(connections)) {
    for (const [outputType, branches] of Object.entries(conns)) {
      if (!outputType.startsWith("ai_")) continue;
      for (const branch of branches || []) {
        for (const edge of branch || []) {
          aiParent[src] = edge.node;
        }
      }
    }
  }

  // Dagre solo recibe nodos del flow main (sin AI children)
  const g = new dagre.graphlib.Graph({ compound: false });
  g.setGraph({
    rankdir: "LR",
    nodesep: 60,
    ranksep: 90,
    marginx: 40,
    marginy: 40,
    ranker: "tight-tree",
  });
  g.setDefaultEdgeLabel(() => ({}));

  const NODE_W = 200;
  const NODE_H = 80;

  for (const n of opNodes) {
    if (aiParent[n.name]) continue; // child, lo posicionamos manualmente despues
    g.setNode(n.name, { width: NODE_W, height: NODE_H });
  }

  // Edges main solamente
  for (const [src, conns] of Object.entries(connections)) {
    if (!opByName[src] || aiParent[src]) continue;
    for (const [outputType, branches] of Object.entries(conns)) {
      if (outputType !== "main") continue;
      for (const branch of branches || []) {
        for (const edge of branch || []) {
          const tgt = edge.node;
          if (!opByName[tgt] || aiParent[tgt]) continue;
          g.setEdge(src, tgt);
        }
      }
    }
  }

  dagre.layout(g);

  // Extraer posiciones (dagre da centros; n8n usa top-left, asi que ajustamos)
  const positions = {};
  for (const name of g.nodes()) {
    const n = g.node(name);
    positions[name] = [Math.round(n.x - NODE_W / 2), Math.round(n.y - NODE_H / 2)];
  }

  // AI children: debajo del padre
  // Agrupar children por padre y apilarlos verticalmente (sub-columna)
  const childrenByParent = {};
  for (const [child, parent] of Object.entries(aiParent)) {
    if (!childrenByParent[parent]) childrenByParent[parent] = [];
    childrenByParent[parent].push(child);
  }
  const AI_OFFSET_Y = 140; // debajo del padre
  const AI_SPACING_X = 180; // entre children del mismo padre
  for (const [parent, children] of Object.entries(childrenByParent)) {
    if (!positions[parent]) continue;
    const [px, py] = positions[parent];
    children.sort();
    const totalW = (children.length - 1) * AI_SPACING_X;
    const startX = px - totalW / 2 + (NODE_W - AI_SPACING_X) / 2;
    children.forEach((child, i) => {
      positions[child] = [Math.round(startX + i * AI_SPACING_X), Math.round(py + AI_OFFSET_Y)];
    });
  }

  // Sticky notes: asignar nodos por heurística de nombre, luego abrazarlos
  function lane(name) {
    const n = name.toLowerCase();
    if (/buffer:|soy el ultimo|preparar mensaje final|descartar \(no soy/.test(n))
      return "Sticky Note - Buffer";
    if (/(switch - tipo mensaje|analizar imagen|obtener media|convert to file|transcribir audio|obtener imagen|convert imagen|set marker|set passthrough|merge multimedia)/.test(n))
      return "Sticky Note - Multimedia";
    if (/(tiene respuesta|descartar \[no_reply\]|evolution - typing|delay humano|split en mensajes|enviar mensaje|guardar msg)/.test(n))
      return "Sticky Note - Salida";
    if (/(webhook|edit fields|filtrar|kill-switch|webhook validator|bot enabled|bot disabled|es comando admin|build redis cmd|es off u on|redis set bot|http send admin|redis get bot|redis get dentalink|dentalink up|rate limit|es fromme|build fromme|postgres - save fromme|chatwoot|verificar label|bot activo|humano atendiendo|check session age|handle stale|clear old memory|es primer)/.test(n))
      return "Sticky Note - Entrada";
    return "Sticky Note - AI Agent";
  }

  const nodesByLane = {};
  for (const n of opNodes) {
    const l = lane(n.name);
    if (!nodesByLane[l]) nodesByLane[l] = [];
    nodesByLane[l].push(n.name);
  }

  const stickyBoxes = {};
  for (const s of stickies) {
    const owned = nodesByLane[s.name] || [];
    if (owned.length === 0) {
      stickyBoxes[s.name] = null;
      continue;
    }
    const xs = owned.map((nm) => positions[nm]?.[0]).filter((v) => v !== undefined);
    const ys = owned.map((nm) => positions[nm]?.[1]).filter((v) => v !== undefined);
    if (xs.length === 0) {
      stickyBoxes[s.name] = null;
      continue;
    }
    const PAD_X = 40;
    const PAD_TOP = 110;
    const PAD_BOTTOM = 60;
    stickyBoxes[s.name] = {
      x: Math.min(...xs) - PAD_X,
      y: Math.min(...ys) - PAD_TOP,
      w: Math.max(...xs) - Math.min(...xs) + NODE_W + 2 * PAD_X,
      h: Math.max(...ys) - Math.min(...ys) + NODE_H + PAD_TOP + PAD_BOTTOM,
    };
  }

  process.stdout.write(JSON.stringify({ positions, stickyBoxes }, null, 2));
});
