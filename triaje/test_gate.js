// triaje/test_gate.js — tests del gate de red flags con mensajes REALES de pacientes
// (sombra retrospectiva 2/9, docs/analisis-retrospectivo-urgencias-2026-09-02.md) +
// casos sintéticos de red flag que en 60 días no aparecieron pero deben escalar.
//
// Correr: node triaje/test_gate.js
const { gateRedFlags } = require("./gate_red_flags.js");

const casos = [
  // --- reales, NO deben disparar (son los que el video podría resolver) ---
  { esperado: false, txt: "Buen día. Como están? Que día puedo acercarme al consultorio? Estoy con mucha molestia debido al exceso de alambre. Me lastima la cara interna" },
  { esperado: false, txt: "Te consulto me pasa q tengo alambre de atrás salido y se incrustó en la parte de atrás" },
  { esperado: false, txt: "Buenas tardes Iris. Cómo estás? Podés decirle a la doc que se soltó el alambre q tengo arriba para poner la Gomita" },
  { esperado: false, txt: "Hola Irina como estas? Vos sabes que le quedó un alambrecito suelto a Justina y le esta lastimando el cachete\nPodra verla un ratito la dra?" },
  { esperado: false, txt: "Hola buen día, a Julia se le cortó el alambre de los brackets de abajo y se le sale cada vez que come, también se le salió una de las gomitas. Tiene turno recién el 7" },
  { esperado: false, txt: "Buenas tardes doctora quería pedirle si me lo puede ver a Abel porque tiene un alambre de punta que aparentemente se le salio lo que usted le pone en la punta para que no le pinche" },
  { esperado: false, txt: "hola buen dia como esta? disculpa a mi  hija se le salio el topecito que esta en su diente de arriba" },
  { esperado: false, txt: "Me olvidé de decirles que se le salió un bracket a Máxima\nLo tiene guardado" },
  { esperado: false, txt: "Buenas tardes \nEs para avisar que a nahiara se le despegó un brackets de la muelita \nMuchas gracias" },
  { esperado: false, txt: "Hola\nMáxima no encuentra el bracket" },
  { esperado: false, txt: "Te queria contar que se me acaba de partir la contención" },
  { esperado: false, txt: "Anoche mi hija estaba cepillando sus alineadores y se partieron en 2. Los de arriba." },
  { esperado: false, txt: "hola raquel ayer me olvidé de mandarte mensaje y es por el tema del bracket de abajo que choca con el colmillo de arriba" },
  { esperado: false, txt: "Buenas starde\nSrta a mí hijita\nLe duele\nUna parte del labio dice que tiene un brackets que le molesta" },
  { esperado: false, txt: "buenas tardes, estuvo bien, pero la cadena del otro micro se me salio" },
  // --- reales, límite (documentan el comportamiento actual, Raquel decide) ---
  { esperado: false, txt: "hola raquel te quería informar que se me salió un alambre de la parte derecha de abajo jugando rugby\nlo tengo salido al alambre", nota: "rugby: hoy NO cuenta como golpe (pendiente Raquel)" },
  { esperado: true,  txt: "Mañana estoy saliendo a jujuy si se puede pasar en caso que puedo podría pasar a verte Raquel? La verdad que el dolor no baja y nose hasta cuando tengo que seguir tomando calmantes", nota: "dolor que no baja + calmantes" },
  { esperado: true,  txt: "Hola si sabes q se me despegó una contención y me está matando la punta del alambre", nota: "hipérbole 'me está matando' (pendiente Raquel)" },
  { esperado: true,  txt: "Buen dia geronimo paso con fiebre y aun no le baja ..no va.disculpe.", nota: "fiebre en una CANCELACIÓN: el gate dispara, por eso solo debe correr dentro del camino de urgencias" },
  // --- sintéticos, DEBEN disparar ---
  { esperado: true,  txt: "Mi hijo se cayó en el colegio y se le partió el bracket, le sangra mucho la boca", flags: ["trauma", "sangrado_abundante"] },
  { esperado: true,  txt: "Se me salió el bracket y creo que me lo tragué", flags: ["tragado"] },
  { esperado: true,  txt: "Tengo la cara hinchada del lado del alambre que pincha", flags: ["hinchazon"] },
  { esperado: true,  txt: "Le cuesta tragar y le duele mucho", flags: ["respirar_tragar"] },
  { esperado: true,  txt: "Tiene fiebre desde anoche y le duele la muela con el bracket", flags: ["fiebre"] },
  { esperado: true,  txt: "Me pegaron un pelotazo y se me aflojó el diente con el bracket", flags: ["trauma"] },
  { esperado: true,  txt: "el dolor es insoportable, no aguanto más", flags: ["dolor_intenso"] },
  // --- sintéticos, NO deben disparar (sangrado leve normal, dolor leve) ---
  { esperado: false, txt: "me sangra un poquito la encía cuando me cepillo con los brackets" },
  { esperado: false, txt: "me molesta un poco el alambre, me raspa el cachete" },
  { esperado: false, txt: "se me soltó la gomita de un bracket" },
];

let fallos = 0;
for (const c of casos) {
  const r = gateRedFlags(c.txt);
  const okEsc = r.escala === c.esperado;
  const okFlags = !c.flags || c.flags.every((f) => r.flags.includes(f));
  const ok = okEsc && okFlags;
  if (!ok) fallos++;
  console.log(`${ok ? "OK  " : "FAIL"} escala=${r.escala} [${r.flags.join(",")}] ${c.nota ? "(" + c.nota + ") " : ""}— «${c.txt.replace(/\n/g, " / ").slice(0, 90)}»`);
}
console.log(`\n${casos.length - fallos}/${casos.length} casos OK`);
process.exit(fallos ? 1 : 0);
