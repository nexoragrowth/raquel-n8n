# Diseño premium del panel — especificación completa (19/10/2026)

> **Para quién:** el ingeniero que construye el panel (`nexora-whatsapp-agent`, Next.js 16 + Tailwind v4 + Phosphor). Está pensada para construirse sin preguntar: cada valor está fijado, y cada pantalla tiene estructura, jerarquía, comportamiento y criterio de listo.
> **De dónde sale:** lectura del panel al 19/10 (`app/globals.css`, `app/layout.tsx`, `app/(app)/layout.tsx`, `components/sidebar.tsx`, `components/ui/*`, `components/conversaciones/*`, páginas de `app/(app)/**`) y del backlog maestro (`docs/backlog-maestro-2026-10-19.md`, épicas DIS, MOB, ATE, CRM, REC y AGE). Esta especificación **es** el entregable de diseño de DIS-02 a DIS-07, MOB-01 y MOB-03, y la parte visual de ATE-03/04/05/07, CRM-03/04/07/08, REC-02/03/05 y AGE-04. Lo que no está acá sigue en el backlog.
> **Pedido de Lucas que manda:** panel premium, mobile primero (la clínica trabaja desde el celular y está a full), y el sistema propio (contactos, familias, recorrido, seguimientos y agenda propia) avanzando ya, no después de febrero. Por eso el plan (§5) construye todas las pantallas nuevas sobre **datos demo y adaptadores** desde el principio. La interfaz no espera al backend: cuando llega la tabla real, se cambia el adaptador y no la pantalla.

---

## 0. Diagnóstico del panel actual (lo que se corrige)

| Problema medido | Dónde | Corrección en esta especificación |
|---|---|---|
| Oscuro forzado (`<html className="dark">`), verde ácido `hsl(142 71% 45%)` y tarjetas con glow. Es un port 1:1 de otro proyecto, nada que ver con una clínica estética que trabaja de día | `app/layout.tsx`, `globals.css` | Claro por defecto, oscuro y sistema (§2.2). Sin glow ni gradiente (§2.6) |
| Blanco sobre el primario da 2,30:1, el badge de no leídos 2,18:1 y el borde 1,22:1 | `globals.css` | Todos los pares verificados ≥ 4,5:1 (texto) y ≥ 3:1 (bordes de controles, foco) (§2.2) |
| Verde = marca = bot = confirmado. El estado depende solo del color (ícono de 13 px) | `conversation-list.tsx`, `chat-view.tsx` | Estados con nombre, ícono y texto propios (§2.2.3, §3.5) |
| A 390 px la barra lateral de 256 px deja ~134 px útiles. No hay versión mobile | `sidebar.tsx`, `(app)/layout.tsx` | Barra inferior de 5 destinos, header de 56 px y rail en tablet (§4.0) |
| 53 usos de texto de 10-11 px, y el input del chat a 14 px (hace zoom en iOS) | toda la app | Mínimo 12 px. Inputs de 16 px en mobile (§2.1) |
| El menú de la lista abre solo con clic derecho. 57 `title=` que en táctil no se ven | `conversation-list.tsx` | Mantener apretado → hoja de acciones, deslizar con deshacer y botón equivalente siempre (§4.1) |
| 5 modales sin trampa de foco, 5 switches y 13 botones primarios hechos a mano | varios | Primitivas únicas sobre Radix (§3) |
| `chat-view.tsx` tiene 2.680 líneas | `components/conversaciones` | Partido en módulos de ≤ 600 líneas (§5, etapa 5) |
| Aviso "agente APAGADO" con emoji, a todo el ancho | `(app)/layout.tsx` | Pastilla persistente "Asiri apagada" que abre una hoja (§4.0) |

---

## 1. Principios y referencias

### 1.1 Los 5 principios

1. **El pulgar primero.** Cada tarea diaria (tomar una urgencia, contestar, marcar un tipo, ver los turnos de mañana) se hace con una mano a 390 px, en 2 toques o menos, con objetivos de 44 × 44 px o más. El escritorio es la versión amplia de la misma pantalla, no otra app.
2. **Estado antes que decoración.** Lo primero que se lee en cualquier fila es quién atiende (Asiri, una persona o nadie) y si hay algo urgente. Cada estado tiene texto, ícono y color, y se entiende también en escala de grises.
3. **Calma clínica.** Fondo claro tipo porcelana, tinta oscura, un solo color de acción (verde azulado) y acentos solo para estados. Sin glow, sin gradientes y sin MAYÚSCULAS. La urgencia se nota porque todo lo demás está en silencio.
4. **Nada se pierde y todo se deshace.** Cada acción es optimista, se confirma con un aviso que trae "Deshacer" (5 s), y si falla vuelve atrás con el motivo en lenguaje llano. Todo lo que escribe en la agenda (agendar, reprogramar, confirmar, cancelar o anular un turno, también en modo práctica) y lo destructivo (silenciar a alguien con turnos, mandar un seguimiento) pide confirmación explícita con vista previa **antes** de ejecutarse. El "Deshacer" no reemplaza esa confirmación (regla del 15/10).
5. **Un sistema, no pantallas sueltas.** Las mismas primitivas, tokens y patrones en todas las rutas: la ficha de contacto, la tarjeta de turno y el chip de estado son siempre los mismos componentes, se abran desde donde se abran.

### 1.2 Referencias concretas (qué se toma de cada app)

| Patrón | App de referencia | Qué se toma exactamente | Dónde se usa |
|---|---|---|---|
| Bandeja de trabajo con triage | **Linear Inbox** | Lista agrupada por estado con contador por grupo, fila de una línea con ícono de estado a la izquierda, atajos `J/K` y `E`, detalle a la derecha sin cambiar de pantalla | Atención (§4.3) |
| Velocidad de teclado y "inbox zero" | **Superhuman** | Paleta de comandos `Cmd/Ctrl+K`, atajos de una tecla mostrados en el tooltip y en el menú (`Kbd`), deshacer inmediato después de cada acción, foco que avanza solo al siguiente ítem al resolver | Conversaciones y Atención en escritorio |
| Inbox + chat + contexto del cliente | **Intercom Inbox** | Tres columnas (lista · conversación · rail con la ficha), composer con selector "responder / nota interna", chips de estado en el header, "asignar a mí" (= Tomar) | Conversaciones (§4.1), Atención |
| Densidad, tablas y estados de datos | **Stripe Dashboard** | Tipografía tabular en montos y horas, encabezados de sección pequeños pero no en mayúsculas, estados vacíos con una acción clara, filtros como chips con contador | Hoy, Recordatorios, Embudo |
| Calma y jerarquía del día | **Things 3** | La vista "Hoy" como lista corta y ordenada con secciones ("Ahora", "Esta tarde", "Mañana"), mucho aire, un solo acento, animaciones de completar breves | Hoy (§4.4), Agenda día mobile |
| Navegación lateral silenciosa y espacios | **Arc** | Barra lateral agrupada y colapsable con secciones con nombre, ítem activo con superficie y no con color fuerte, atajo para colapsar | Barra lateral de escritorio (§4.0) |
| Ficha de persona con relaciones | **Attio** (complementaria) | Cabecera con identidad + atributos editables en línea, pestañas o secciones de actividad, chips de relación con otra ficha | Ficha de contacto (§4.2) |
| Agenda del día y de la semana | **Cal.com** (complementaria) | Columna de horas con huecos visibles, bloque del turno con estado por forma, hoja de detalle con acciones | Agenda (§4.5) |
| Burbujas y lectura del chat | **WhatsApp Business** | Lado izquierdo para el paciente y derecho para la clínica, agrupado por minuto, separador de día fijo arriba, tildes de entrega. Es el modelo mental de la secretaria: no hay que reeducarla | Chat (§3.10) |
| Hoja inferior arrastrable | **Apple Maps / iOS** | Hoja con agarradera, dos alturas (media y completa), cierre arrastrando hacia abajo, fondo atenuado | Todas las hojas mobile (§3.15) |

---

## 2. Sistema de diseño (valores)

### 2.1 Tipografía

**Familia única: Inter** (Google Fonts, variable, con eje `opsz`), cargada con `next/font/google`:

```ts
// app/layout.tsx
import { Inter } from "next/font/google";
const inter = Inter({ subsets: ["latin"], axes: ["opsz"], variable: "--font-sans", display: "swap" });
```

- **Fallback:** `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`.
- **Alternativa evaluada** (para la muestra de DIS-02): **Geist** (Google Fonts). Se elige Inter porque tiene más pesos y glifos probados en interfaces densas, y su `opsz` mejora las tallas de 12-14 px.
- **Se elimina** Plus Jakarta Sans y Space Mono. Las horas, montos, contadores y KPIs usan `font-variant-numeric: tabular-nums` (utilidad `tabular-nums`).
- **Pesos permitidos:** 400 (texto), 500 (énfasis, botones, nombres), 600 (títulos y números grandes). No se usa 700.
- **Mayúsculas:** prohibidas en rótulos y encabezados (`uppercase` = 0 en el código).
- **`font-feature-settings`:** `"cv11", "ss01"` (a de un piso y dígitos más claros) en `html`.

**Escala con nombre** (rem sobre base 16 px). Mobile < 768 px y escritorio ≥ 1024 px. Lo que no cambia se indica con "=".

| Token | Uso | Mobile: tamaño / interlineado | Escritorio | Peso | Tracking |
|---|---|---|---|---|---|
| `text-caption` | Hora de la burbuja, meta, contadores, rótulo de la barra inferior | 12 px (0,75 rem) / 16 px | = | 500 | 0 |
| `text-footnote` | Texto secundario de la fila, ayuda de un campo | 14 px (0,875 rem) / 20 px | 13 px (0,8125 rem) / 18 px | 400 | 0 |
| `text-body` | Texto de lectura, burbujas, inputs | **16 px (1 rem) / 24 px** | 14 px (0,875 rem) / 20 px | 400 | −0,006 em |
| `text-callout` | Nombre en la fila, botones, ítems de menú | 16 px / 22 px | 14 px / 20 px | 500 | −0,006 em |
| `text-headline` | Título de tarjeta, nombre en el header del chat | 17 px (1,0625 rem) / 24 px | 15 px (0,9375 rem) / 22 px | 600 | −0,011 em |
| `text-title-3` | Título de sección dentro de una página | 18 px (1,125 rem) / 26 px | = | 600 | −0,014 em |
| `text-title-2` | Título de página | 22 px (1,375 rem) / 28 px | 24 px (1,5 rem) / 30 px | 600 | −0,017 em |
| `text-title-1` | Saludo de Hoy, nombre en la ficha | 28 px (1,75 rem) / 34 px | 30 px (1,875 rem) / 36 px | 600 | −0,021 em |
| `text-display` | KPIs grandes (siempre con `tabular-nums`) | 34 px (2,125 rem) / 40 px | = | 600 | −0,022 em |

**Reglas duras:**
- Nada mide menos de 12 px a 390 px (se verifica con Playwright).
- `input`, `textarea` y `select` usan `text-body` en mobile, o sea 16 px, para que iOS no haga zoom.
- Las burbujas del chat usan siempre 16 px en mobile y 15 px en escritorio (excepción a `text-body` de escritorio: el chat se lee, no se escanea).
- Ancho de lectura máximo: 68 caracteres (`max-w-[68ch]`) en Conocimiento y textos largos.
- Se reemplazan todos los `text-[10px]`, `text-[11px]` y `text-xs` sueltos por tokens con nombre: un grep de `text-\[\d+px\]` debe dar 0.

### 2.2 Color

Dirección **"Porcelana y tinta"** (DIS-02): fondo frío casi blanco, texto tinta azul-negra, acción en verde azulado profundo, dorado solo para la marca de la clínica (logo, firma, nunca en controles). Valores en hex. **Cada par está medido** con la fórmula WCAG 2.x (script en `scripts/contraste.mjs`, §5 etapa 1). Mínimos: 4,5:1 para texto, 3:1 para bordes de controles, foco e íconos sin texto.

#### 2.2.1 Neutros y acción

| Token | Uso | Claro | Oscuro |
|---|---|---|---|
| `--bg` | Fondo de la app | `#F6F7F9` | `#0D1015` |
| `--surface` | Tarjetas, listas, header, barra inferior | `#FFFFFF` | `#151920` |
| `--surface-sunken` | Campos, filas seleccionadas en reposo, tracks | `#EEF0F3` | `#1B2029` |
| `--surface-raised` | Hojas, diálogos, menús, toasts | `#FFFFFF` (+ sombra 3) | `#1C212B` |
| `--border` | Divisores y bordes decorativos (no son el único indicio de nada) | `#DDE1E7` | `#2A303B` |
| `--border-strong` | Borde de inputs, checkbox, botón secundario | `#848D9C` | `#6B7484` |
| `--text-1` | Texto principal | `#121722` | `#E9ECF1` |
| `--text-2` | Texto secundario | `#465061` | `#AEB5C1` |
| `--text-3` | Terciario: horas, meta, placeholder | `#5F6878` | `#9099A7` |
| `--primary` | Botón primario, enlace, selección, foco | `#0E6B66` | `#3DB5AA` |
| `--primary-hover` | Hover y pressed del primario | `#0B5853` | `#5CC7BD` |
| `--on-primary` | Texto sobre el primario | `#FFFFFF` | `#05201D` |
| `--primary-soft` | Fondo de ítem activo, chip activo | `#E2F0EE` | `#12302D` |
| `--primary-text` | Texto sobre `--primary-soft` y enlaces | `#0B5C57` | `#6FD0C6` |
| `--focus` | Anillo de foco (2 px + 2 px de separación) | `#0E6B66` | `#5CC7BD` |
| `--brand` | Marca de la clínica (logo, firma). **Nunca en controles ni estados** | `#9A6B12` | `#D2A54E` |
| `--overlay` | Velo detrás de hojas y diálogos | `rgb(18 23 34 / 0.40)` | `rgb(0 0 0 / 0.60)` |

**Contrastes medidos (claro):** `text-1`/`bg` 16,72 · `text-1`/`surface` 17,93 · `text-2`/`surface` 8,14 · `text-2`/`bg` 7,59 · `text-3`/`surface` 5,62 · `text-3`/`bg` 5,24 · `text-3`/`sunken` 4,92 · `on-primary`/`primary` 6,34 · `on-primary`/`primary-hover` 8,28 · `primary-text`/`primary-soft` 6,68 · `text-3`/`primary-soft` 4,80 · `border-strong`/`surface` 3,35 · `border-strong`/`bg` 3,12 · `focus`/`bg` 5,91 · `brand`/`surface` 4,68.
**Contrastes medidos (oscuro):** `text-1`/`bg` 16,09 · `text-1`/`surface` 14,88 · `text-2`/`surface` 8,54 · `text-3`/`surface` 6,13 · `text-3`/`sunken` 5,68 · `on-primary`/`primary` 6,82 · `primary-text`/`primary-soft` 7,75 · `text-3`/`primary-soft` 4,91 · `border-strong`/`surface` 3,74 · `border-strong`/`bg` 4,04 · `focus`/`bg` 9,40 · `brand`/`surface` 7,75.

#### 2.2.2 Superficie del chat

| Token | Uso | Claro | Oscuro | Texto `text-1` | Meta `text-3` |
|---|---|---|---|---|---|
| `--chat-bg` | Fondo de la línea de tiempo | `#EEF1F4` | `#11151B` | 15,81 / 15,46 | 4,96 / 6,37 |
| `--bubble-patient` | Paciente (izquierda) + borde 1 px `--border` en claro | `#FFFFFF` | `#1E232C` | 17,93 / 13,31 | 5,62 / 5,48 |
| `--bubble-asiri` | Asiri (derecha) | `#E9F3F1` | `#15302D` | 15,84 / 11,88 | 4,96 / 4,89 |
| `--bubble-staff` | Persona de la clínica (derecha) | `#E7EEFA` | `#172840` | 15,37 / 12,54 | 4,82 / 5,16 |

Asiri y la persona no se distinguen solo por el tono: llevan rótulo con ícono (§3.10).

#### 2.2.3 Estados (nombre fijo, nunca se reutilizan para otra cosa)

Cada estado tiene tres valores: `fg` (texto e ícono sobre `surface`), `soft` (fondo del chip) y `solid` (fondo sólido, solo para el botón o el badge de prioridad) con su `on-solid`.

| Estado | Ícono Phosphor (peso `fill`) | Claro fg / soft | Oscuro fg / soft | Sólido claro (texto) | Sólido oscuro (texto) | Contraste fg/soft (claro · oscuro) |
|---|---|---|---|---|---|---|
| `bot` — Asiri atiende | `RobotIcon` | `#5B47C8` / `#EEEBFB` | `#A79BFF` / `#231F3D` | `#5B47C8` (`#FFF`) 6,60 | `#A79BFF` (`#120B33`) 7,83 | 5,63 · 6,57 |
| `human` — atiende una persona | `UserIcon` | `#1D5BB8` / `#E6EFFB` | `#7EB0FF` / `#16263F` | `#1D5BB8` (`#FFF`) 6,48 | `#7EB0FF` (`#06182F`) 8,09 | 5,59 · 6,90 |
| `muted` — silenciado (Asiri no contesta) | `SpeakerSimpleSlashIcon` | `#556070` / `#ECEEF1` | `#A3ABB8` / `#232832` | — | — | 5,49 · 6,39 |
| `urgent` — urgencia | `FirstAidKitIcon` | `#B42318` / `#FDECEA` | `#FF8A80` / `#3A1715` | `#B42318` (`#FFF`) 6,57 | `#FF8A80` (`#2A0A07`) 8,03 | 5,75 · 7,00 |
| `payment` — pago / comprobante | `CurrencyCircleDollarIcon` | `#11734A` / `#E3F4EB` | `#5FD39A` / `#11301F` | `#11734A` (`#FFF`) 5,87 | — | 5,15 · 7,69 |
| `attention` — requiere secretaria / pendiente | `HandWavingIcon` | `#8A5300` / `#FDF1DC` | `#F2B65A` / `#33240C` | — | — | 5,66 · 8,31 |

**Estados de turno** (reusan la paleta, pero se distinguen **por forma**, no por color):

| Estado del turno | Forma del marcador | Color | Texto |
|---|---|---|---|
| Confirmado | Círculo relleno + `CheckCircleIcon` fill | `payment.fg` | "Confirmado" |
| Pendiente de confirmar | Círculo con contorno de 2 px | `attention.fg` | "Sin confirmar" |
| Anulado | Bloque con borde punteado y texto tachado | `muted.fg` | "Anulado" |
| No asistió | `XCircleIcon` regular | `urgent.fg` | "No vino" |
| Atendido | `CheckIcon` sin círculo | `text-3` | "Atendido" |

#### 2.2.4 Tintes de avatar (iniciales)

Seis tintes estables por hash del teléfono (como hoy, pero con texto oscuro sobre fondo suave, medido):

| # | Claro: texto / fondo | Contraste | Oscuro: texto / fondo | Contraste |
|---|---|---|---|---|
| 1 verde azulado | `#0B5C57` / `#D5EBE8` | 6,29 | `#B3EDE6` / `#1A3C39` | 9,25 |
| 2 violeta | `#4A3AA8` / `#E4E0FA` | 6,64 | `#D2CBFF` / `#2C2650` | 9,15 |
| 3 azul | `#1A4F9E` / `#DCE8FA` | 6,39 | `#BCD6FF` / `#1B3152` | 8,83 |
| 4 ámbar | `#7A4A00` / `#FBE8C8` | 6,23 | `#FFD9A0` / `#3D2C10` | 10,01 |
| 5 coral | `#9E1F16` / `#FADBD7` | 6,08 | `#FFC2BB` / `#45201C` | 9,27 |
| 6 pizarra | `#3F4A5A` / `#E3E6EB` | 7,18 | `#D3D8E0` / `#2B313C` | 9,13 |

#### 2.2.5 Temas e implementación

- **Claro por defecto**, más **Oscuro** y **Sistema** (Configuración → Apariencia; hasta la etapa 12, en el menú de cuenta y en la hoja "Más"). La preferencia se guarda en `localStorage` (`asiri:tema`) dentro de `try/catch`. Si falla, se usa "sistema".
- **Sin parpadeo:** un script inline en `<head>` (antes del CSS) lee la preferencia, resuelve "sistema" con `matchMedia('(prefers-color-scheme: dark)')` y pone `data-theme="light|dark"` en `<html>`. Se escucha el cambio del sistema solo si la preferencia es "sistema".
- **Tailwind v4:** `@custom-variant dark (&:where([data-theme=dark], [data-theme=dark] *));` y tokens en `:root` / `[data-theme=dark]`, mapeados en `@theme inline` (`--color-surface: var(--surface)`, etc.). Se borran las variables HSL heredadas (`--status-*`, `--accent-*`, `--nexora-*`, `--sidebar-*`) y las utilidades `card-glow`, `btn-glow`, `text-gradient` y `glass-panel`.
- **Colores crudos de Tailwind prohibidos** (`amber-500`, `emerald-600`, `bg-white`, etc.): un grep de `(bg|text|border)-(red|amber|emerald|sky|violet|rose|teal|indigo|fuchsia|green|blue)-\d` debe dar 0 fuera de `globals.css`.
- **`theme-color`** en el viewport: `#FFFFFF` claro, `#151920` oscuro (es el color de `--surface`, que es el header y la barra inferior).

### 2.3 Espaciado

Grilla de 4 px. Escala única (la de Tailwind v4 con `--spacing: 0.25rem` ya es de 4 px; se usan **solo** estos pasos):

| Paso | px | Uso típico |
|---|---|---|
| 0.5 | 2 | Entre burbujas del mismo grupo |
| 1 | 4 | Ícono ↔ texto en chips |
| 2 | 8 | Ícono ↔ texto en botones, gap de chips |
| 3 | 12 | Padding vertical de filas compactas, entre grupos de burbujas |
| 4 | 16 | **Margen lateral mobile**, padding de tarjeta mobile |
| 5 | 20 | Padding de tarjeta escritorio |
| 6 | 24 | Margen lateral escritorio, separación entre secciones mobile |
| 8 | 32 | Separación entre secciones escritorio |
| 10 | 40 | Encabezado de página escritorio (arriba) |
| 12 | 48 | Objetivo táctil grande |
| 16 | 64 | Aire de estados vacíos |

Medidas fijas: header mobile **56 px**, barra inferior **64 px + `env(safe-area-inset-bottom)`**, fila de lista **72 px** mobile / **60 px** escritorio, barra lateral **240 px** (colapsada **64 px**), rail de tablet **72 px**, lista de conversaciones en escritorio **360 px**, rail de contexto **340 px**, ancho máximo de página de contenido **1120 px**.

### 2.4 Radios

| Token | Valor | Uso |
|---|---|---|
| `--radius-xs` | 6 px | Badges, `Kbd`, marcadores de turno |
| `--radius-sm` | 10 px | Botones, inputs, select, ítems de menú, filas seleccionadas |
| `--radius-md` | 16 px | Tarjetas, burbujas (con 4 px en la esquina de la colita), diálogos |
| `--radius-lg` | 24 px | Borde superior de las hojas mobile |
| `--radius-full` | 9999 px | Chips, avatares, pastillas, badges de contador |

### 2.5 Iconografía (Phosphor)

- Librería: `@phosphor-icons/react` (ya instalada). En Server Components, `@phosphor-icons/react/dist/ssr`.
- **Tamaños:** 16 px (meta, dentro de chips y badges) · 20 px (por defecto en botones y la barra lateral) · 24 px (barra inferior, acciones del header mobile) · 32 px (encabezado de tarjetas vacías) · 48 px (estados vacíos de página).
- **Pesos:** `regular` por defecto. `fill` para el ítem activo de la navegación y para los chips de estado. `bold` solo a 16 px cuando el ícono va solo dentro de un control chico. `duotone` solo en ilustraciones de estados vacíos.
- **Íconos decorativos** con `aria-hidden`. Un `IconButton` exige `aria-label` (es obligatorio en el tipo).
- **Mapa fijo** (se usa siempre el mismo):

| Concepto | Ícono |
|---|---|
| Hoy | `SunHorizonIcon` |
| Atención | `TrayIcon` |
| Conversaciones / Chats | `ChatsCircleIcon` |
| Agenda | `CalendarBlankIcon` |
| Contactos | `AddressBookIcon` |
| Familia | `UsersThreeIcon` |
| Recorrido / embudo | `FunnelSimpleIcon` |
| Seguimientos | `PaperPlaneTiltIcon` |
| Recordatorios | `BellIcon` |
| Conocimiento | `BookOpenTextIcon` |
| El agente (Asiri) | `RobotIcon` |
| Servicios | `TagIcon` |
| Aprendizaje | `LightbulbIcon` |
| Estado del sistema | `PulseIcon` |
| Configuración | `GearSixIcon` |
| Más (barra inferior) | `DotsThreeCircleIcon` |
| Tomar | `HandGrabbingIcon` |
| Resolver | `CheckCircleIcon` |
| Devolver a Asiri | `ArrowUUpLeftIcon` |
| Esperando al paciente | `HourglassMediumIcon` |
| Por clasificar | `QuestionIcon` |
| Acciones rápidas del chat | `LightningIcon` |

### 2.6 Sombras y elevación

Tres niveles, sin glow ni color. En oscuro la elevación se marca sobre todo por la superficie más clara y un borde interior.

| Nivel | Uso | Claro | Oscuro |
|---|---|---|---|
| 0 | Superficies planas (listas, header) | ninguna, separadas por `--border` | ninguna |
| 1 | Tarjetas | `0 1px 2px rgb(18 23 34 / .06), 0 1px 1px rgb(18 23 34 / .04)` | `inset 0 0 0 1px rgb(255 255 255 / .04)` |
| 2 | Menús, popovers, tarjeta arrastrada | `0 4px 12px rgb(18 23 34 / .08), 0 1px 3px rgb(18 23 34 / .06)` | `0 4px 16px rgb(0 0 0 / .45), inset 0 0 0 1px rgb(255 255 255 / .06)` |
| 3 | Hojas, diálogos, toasts | `0 16px 40px rgb(18 23 34 / .14), 0 2px 6px rgb(18 23 34 / .08)` | `0 16px 48px rgb(0 0 0 / .60), inset 0 0 0 1px rgb(255 255 255 / .08)` |

**Escala de z-index:** contenido 0 · sticky (separador de día, encabezados de grupo) 10 · header 20 · barra inferior y lateral 30 · menús y popovers 40 · velo 50 · hoja/diálogo 51 · toast 60 · pastilla "Asiri apagada" 65.

### 2.7 Movimiento

| Token | Duración | Curva | Uso |
|---|---|---|---|
| `--dur-fast` | 120 ms | `cubic-bezier(0.2, 0, 0, 1)` | Hover, pressed, cambio de chip, check |
| `--dur-base` | 200 ms | `cubic-bezier(0.2, 0, 0, 1)` | Abrir menú, toast, aparición de fila nueva, cambio de pestaña |
| `--dur-slow` | 320 ms | `cubic-bezier(0.32, 0.72, 0, 1)` (curva de las hojas de iOS) | Hoja inferior, empuje lista → chat en mobile, diálogo |
| `--ease-exit` | 160 ms | `cubic-bezier(0.3, 0, 0.8, 0.15)` | Todo lo que sale (dura menos que lo que entra) |

- **Solo hay movimiento en respuesta a una acción.** No hay animaciones decorativas, en bucle ni al hacer scroll. El único bucle permitido es el spinner (y el pulso de los esqueletos).
- **Fila que se resuelve en Atención:** se colapsa en altura (200 ms) y la siguiente sube. El foco pasa a la siguiente.
- **Deslizar en la lista:** la fila sigue al dedo 1:1. Pasado el umbral de 30% del ancho (o 600 px/s) se completa con `--dur-base`. Si no, vuelve con `--dur-fast`.
- **`prefers-reduced-motion: reduce`:** todas las transiciones de `transform` pasan a `opacity` de 120 ms o a nada. Las hojas aparecen sin deslizar. Se borra el pulso de los esqueletos (quedan estáticos). Se implementa con `@media (prefers-reduced-motion: reduce) { :root { --dur-base: 0ms; --dur-slow: 0ms; } }` más la clase `motion-safe:` de Tailwind en cada `transform`.

### 2.8 Densidad

Dos densidades, elegidas por punto de quiebre (no por preferencia):

| | Cómodo (mobile < 768 px y tablet) | Compacto (escritorio ≥ 1024 px) |
|---|---|---|
| Objetivo táctil mínimo | 44 × 44 px (48 en botones de acción principal) | 32 × 32 px (cumple 24 × 24 de WCAG 2.2 2.5.8) |
| Alto de botón | `md` 44 px · `lg` 48 px | `sm` 32 px · `md` 36 px |
| Alto de input | 48 px | 36 px |
| Fila de lista | 72 px | 60 px |
| Texto base | 16 px | 14 px |
| Margen lateral | 16 px | 24 px |

**Puntos de quiebre:** mobile 0-767 (diseño a **390**, mínimo **360**) · tablet 768-1023 (rail de íconos) · escritorio 1024-1439 · ancho ≥ 1440 (diseño a **1440**, aparece el rail de contexto fijo en Conversaciones).

---

## 3. Componentes base (con estados)

Todos viven en `components/ui/`, se construyen sobre **Radix UI** (Dialog, DropdownMenu, Popover, Tooltip, Select, Switch, Toggle Group) con los tokens de §2, y se muestran todos juntos en `/design` (ruta solo para admin, con selector de tema y de densidad). Para la hoja arrastrable se usa **vaul** (versión fija en `package.json`). Para la paleta de comandos, **cmdk**. Para la virtualización, **@tanstack/react-virtual**.

Convenciones para todos los estados:
- **Foco:** `outline: 2px solid var(--focus); outline-offset: 2px` solo en `:focus-visible`.
- **Deshabilitado:** `opacity: .5`, `cursor: not-allowed` y `aria-disabled`. **Nunca** se deshabilita sin decir por qué: hay un texto de ayuda visible (no solo un tooltip).
- **Cargando:** el control mantiene su ancho (sin saltos), muestra `Spinner` de 16 px en lugar del ícono y tiene `aria-busy="true"`. El texto cambia a gerundio ("Tomando…").
- **Error:** borde o fondo `urgent`, mensaje debajo en `text-footnote` + `urgent.fg`, con `role="alert"` y `aria-describedby`.

### 3.1 Botón (`Button`, `IconButton`)

Variantes: `primary` (fondo `--primary`, texto `--on-primary`) · `secondary` (fondo `--surface`, borde 1 px `--border-strong`, texto `--text-1`) · `ghost` (sin fondo, texto `--text-2`) · `danger` (fondo `urgent.solid`, texto blanco) · `danger-ghost` (texto `urgent.fg`).
Tamaños: `sm` 32 px (padding 0 12, `text-footnote` 500) · `md` 36 px escritorio / 44 px mobile (padding 0 16, `text-callout`) · `lg` 48 px (padding 0 20, `text-callout`, ancho completo en mobile). `IconButton`: cuadrado del mismo alto, ícono 20 (24 en mobile), `aria-label` obligatorio.

| Estado | primary | secondary | ghost |
|---|---|---|---|
| default | `--primary` | `--surface` + borde `--border-strong` | transparente, texto `--text-2` |
| hover (solo con puntero fino) | `--primary-hover` | fondo `--surface-sunken` | fondo `--surface-sunken`, texto `--text-1` |
| focus-visible | anillo `--focus` | anillo `--focus` | anillo `--focus` |
| active (pressed) | `--primary-hover` + `scale(.98)` 120 ms | `--surface-sunken` + `scale(.98)` | `--surface-sunken` |
| disabled | 50% + ayuda visible | 50% | 50% |
| loading | spinner + gerundio, mismo ancho | ídem | ídem |

Un solo `primary` por vista (en una hoja o una tarjeta: uno por contenedor). Con `Kbd` opcional a la derecha en escritorio (ej. "Resolver `E`").

### 3.2 Input y Textarea (`Input`, `Textarea`)

- Alto 48 px mobile / 36 px escritorio, radio `sm`, fondo `--surface`, borde 1 px `--border-strong`, padding 0 14, texto `text-body` (16 px mobile).
- Rótulo arriba (`text-footnote` 500 `--text-2`), siempre visible: el placeholder no es rótulo. Ayuda debajo en `text-footnote` `--text-3`.
- Slot de ícono a la izquierda (20 px, `--text-3`) y botón de limpiar a la derecha (`XCircleIcon` fill 20, solo con valor).
- `Textarea` crece con el contenido (`field-sizing: content` con fallback por JS) de 1 a 6 líneas y después hace scroll.

| Estado | Visual |
|---|---|
| default | borde `--border-strong` |
| hover | borde `--text-3` |
| focus | borde `--primary` + anillo de 3 px `--primary` al 20% (`box-shadow`) |
| filled | igual que default con valor |
| disabled | fondo `--surface-sunken`, texto `--text-3` |
| read-only | fondo `--surface-sunken`, sin borde, texto `--text-1` (para datos que vienen de Dentalink) |
| error | borde `urgent.fg`, ícono `WarningCircleIcon` y mensaje debajo |
| loading (búsqueda) | spinner de 16 px en el slot derecho |

### 3.3 Select (`Select`)

- **Mobile:** `<select>` nativo con el mismo estilo que `Input` y un `CaretDownIcon` de 20 px (el selector nativo de iOS y Android es el mejor para el pulgar).
- **Escritorio:** Radix Select. Lista de opciones con nivel 2, opción de 36 px, check (`CheckIcon` 16) en la elegida, búsqueda si hay más de 8.
- **Opciones con consecuencia** (como el tipo de contacto, que silencia): cada opción muestra debajo, en `text-footnote` `--text-3`, la consecuencia ("Asiri no le contesta"). En mobile, en lugar del select nativo, se abre una hoja con opciones de 56 px y la consecuencia visible.
- Estados: los de `Input` + `open` (borde `--primary`).

### 3.4 Chip de filtro (`FilterChip`) y control segmentado (`Segmented`)

- `FilterChip`: alto 32 px (36 px mobile), radio `full`, padding 0 12, `text-footnote` 500. Contador opcional a la derecha (`tabular-nums`, fondo `--surface-sunken`, radio `full`, mínimo 20 px).
  - default: fondo `--surface`, borde `--border`, texto `--text-2`.
  - hover: fondo `--surface-sunken`.
  - selected (`aria-pressed="true"`): fondo `--primary-soft`, texto `--primary-text`, borde transparente, `CheckIcon` de 16 delante.
  - focus: anillo. Disabled: 50%.
  - Contador en 0: se oculta (el chip no se oculta).
  - Fila de chips con scroll horizontal **interno** (`overflow-x: auto`, sin barra), nunca de la página. Degradado de 16 px en el borde derecho cuando hay más.
- `Segmented` (Día / Semana, Lista / Tablero): track `--surface-sunken`, segmento elegido `--surface` con sombra 1, alto 36 px, radio `sm`. Radix Toggle Group con `type="single"`.

### 3.5 Chip de estado (`StatusChip`) y badge de tipo de contacto (`ContactTypeBadge`)

**`StatusChip`** (quién atiende y prioridad). Alto 24 px (28 px mobile), radio `full`, padding 0 8, ícono 16 `fill` + texto `text-caption` 500, colores `fg`/`soft` del estado (§2.2.3). **Siempre lleva texto**, salvo en el rail colapsado, donde va con `aria-label`.

| Variante | Texto | Texto con detalle (opcional) |
|---|---|---|
| `bot` | "Asiri" | — |
| `human` | "Persona" | "Irina · vuelve en 42 min" (cuenta regresiva del modo humano de 1 h) |
| `muted` | "Silenciado" | "Proveedor · Irina 21/10" (leyenda de CRM-03) |
| `urgent` | "Urgencia" | "Urgencia · hace 3 min" |
| `payment` | "Pago" | "Comprobante recibido" |
| `attention` | "Secretaria" | "Pidió hablar con una persona" |

**`ContactTypeBadge`** (qué es la persona). Alto 22 px, radio `xs`, fondo `--surface-sunken`, texto `text-caption` 500 `--text-2`, sin color de estado (el tipo es dato, no alerta). Si el tipo silencia, lleva delante `SpeakerSimpleSlashIcon` de 16 px y el texto va en `muted.fg`.

| Tipo (`lib/tipos-contacto.ts`) | Texto del badge | ¿Silencia? |
|---|---|---|
| sin tipo (paciente o nuevo) | no se muestra en la lista; en la ficha: "Paciente" o "Nuevo" (sin ficha) | no |
| `familiar` | "Familiar" | no |
| `interno` | "Equipo" | sí |
| `colega` | "Colega" | sí |
| `proveedor` | "Proveedor" | sí |
| `no_paciente` | "No paciente" | sí |
| (CRM) prospecto | "Prospecto" | no |
| (CRM) familia | "Familia · 2 fichas" con `UsersThreeIcon` | no |

Estados del badge: default · hover (si es editable: fondo `--border`, cursor) · focus · loading (spinner reemplaza el ícono) · error (borde `urgent.fg` + aviso al lado: "No se guardó. Reintentar").

### 3.6 Avatar (`Avatar`)

- Tamaños: 24 (menciones) · 32 (rail y tarjetas compactas) · 40 (fila escritorio, header escritorio) · 48 (fila mobile) · 72 (ficha de contacto).
- Contenido: foto de WhatsApp (`/api/foto/[tel]`, como hoy) o iniciales en uno de los 6 tintes (§2.2.4), `text-callout` 600 a 40-48 px (tamaño de letra = 0,4 × el avatar).
- Estados: **cargando** = círculo `--surface-sunken` (sin spinner) · **foto que falla** = iniciales, sin parpadeo · **sin nombre** = últimos 2 dígitos del teléfono (como hoy) · **grupo/familia** = dos avatares superpuestos de 28 px con borde de 2 px `--surface`.
- **Indicador de quién atiende** sobre el avatar: no se usa. El estado va en el `StatusChip` con texto (principio 2).

### 3.7 Item de lista de chat (`ConversationRow`)

```
Mobile (390 × 72)                                        Escritorio (360 × 60)
┌──────────────────────────────────────────────────┐   ┌────────────────────────────────────┐
│ (AV48)  Mariela Gómez · Familiar        14:32     │   │(AV40) Mariela Gómez       14:32    │
│         [Urgencia] Le duele, no come…      (3)    │   │       [Urgencia] Le duele, no…  (3)│
└──────────────────────────────────────────────────┘   └────────────────────────────────────┘
```

- Línea 1: nombre (`text-callout`, 600 si hay no leídos, 500 si no), `ContactTypeBadge` si tiene tipo, y la hora a la derecha (`text-caption` `tabular-nums` `--text-3`; si hay no leídos, `--primary-text` 600).
- Línea 2: `StatusChip` **solo si no es `bot`** (Asiri atendiendo es lo normal y no se marca: así lo distinto se ve) + vista previa en `text-footnote` `--text-2` en una línea con elipsis. A la derecha, badge de no leídos: mínimo 20 × 20 px, radio `full`, fondo `--primary`, texto `--on-primary` `text-caption` 600 `tabular-nums`, "99+" como tope.
- Prefijo de la vista previa según el autor del último mensaje: "Asiri: …", "Irina: …" o sin prefijo si es el paciente.
- Separador: 1 px `--border` desde el borde del texto (no desde el avatar), como iOS.

| Estado | Visual |
|---|---|
| default | fondo `--surface` |
| hover (escritorio) | fondo `--surface-sunken` |
| focus-visible | anillo interior de 2 px `--focus` |
| active (la conversación abierta) | fondo `--primary-soft`, barra de 3 px `--primary` a la izquierda |
| pressed (táctil) | fondo `--surface-sunken` durante el toque |
| no leída | nombre 600, hora en `--primary-text`, badge de contador |
| deslizando | detrás aparece la acción (§4.1, gestos) con su color y su ícono de 24 |
| cargando (esqueleto) | §3.16 |
| vacío (no hay chats en ese filtro) | `EmptyState` con el filtro nombrado: "No hay chats sin leer" y el botón "Ver todos" |
| error al cargar | `ErrorState` en la lista con "Reintentar"; si hay datos viejos, se mantienen con un banner fino "Sin conexión, mostrando lo último" |

### 3.8 Header de chat (`ChatHeader`)

```
Mobile (56 px)
┌──────────────────────────────────────────────────┐
│ ‹  (AV32) Mariela Gómez               (⌕) (⋯)    │
│           [Persona · vuelve en 42 min]            │
└──────────────────────────────────────────────────┘
Escritorio (64 px)
┌──────────────────────────────────────────────────────────────────────────────────┐
│ (AV40) Mariela Gómez · Familiar   [Persona · Irina · 42 min]  [Devolver a Asiri] (⌕) (ⓘ) │
│        +54 9 388 000-1234                                                          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Mobile:** botón Atrás (44 × 44, `CaretLeftIcon` 24), avatar 32, nombre `text-headline` en una línea, debajo `StatusChip` con detalle. Tocar el bloque nombre + chip abre la **hoja de contexto** (ficha resumida, §4.2). A la derecha: buscar y `⋯` (hoja de acciones: Devolver a Asiri / Pasar a persona, Tipo de contacto, Editar nombre, Marcar no leído, Ver ficha completa).
- **Escritorio:** nombre + badge de tipo + teléfono debajo (`text-footnote` `--text-3`), `StatusChip` con detalle, **un solo** botón de modo: si atiende Asiri, `secondary` "Atender yo" (`H`); si atiende una persona, `primary` "Devolver a Asiri" (`B`). Buscar (`/`) y mostrar u ocultar el rail de contexto (`]`).
- Se elimina del header: el switch suelto, el `select` del tipo (pasa al rail o a la hoja) y el lápiz del alias (pasa a la ficha y al menú `⋯`).
- Estados: **aplicando el cambio de modo** = el chip muestra spinner y gerundio ("Devolviendo…") y el botón queda en loading · **error** = el chip vuelve al estado anterior y aparece un toast de error con "Reintentar" · **Asiri apagada globalmente** = el chip dice "Asiri apagada" en `attention` y el botón "Devolver a Asiri" se reemplaza por un enlace a Estado.
- Franja de casos abiertos (ATE-03): si el contacto tiene un caso abierto en Atención, debajo del header aparece una franja de 40 px: `[Urgencia] Dolor, aparato salido · hace 3 min · [Tomar] [Resolver]`.

### 3.9 Composer (`ChatComposer`)

- Fijo abajo, por encima del teclado (`useVisualViewport` en iOS) y del `safe-area-inset-bottom`. Fondo `--surface`, borde superior `--border`, padding 8 12.
- `[⚡] [ textarea 16 px, 1-6 líneas, radio 20, fondo --surface-sunken ] [📎] [➤]`. Los íconos son `LightningIcon` (acciones rápidas aprobadas, REC-06), `PaperclipIcon` y `PaperPlaneRightIcon` en un botón circular de 44 px `primary` que solo se activa con texto.
- Escritorio: `Enter` envía, `Shift+Enter` hace salto de línea, `/` en un campo vacío abre las acciones rápidas.
- **Aviso al escribir con Asiri atendiendo:** "Si mandás un mensaje, Asiri deja de responder en este chat por 1 hora" (`text-footnote` `attention.fg`, encima del campo, solo la primera vez por chat).
- Estados: vacío (enviar deshabilitado) · escribiendo · enviando (burbuja optimista con `ClockIcon` de 16 px en la meta) · enviado (un tilde) · entregado (dos) · leído (dos en `--primary-text`) · error (burbuja con borde `urgent.fg` y "No se envió. Tocá para reintentar") · deshabilitado (contacto sin WhatsApp o canal caído: texto explicativo en lugar del campo).

### 3.10 Burbuja de chat (`ChatBubble`)

| Autor | Lado | Fondo | Rótulo (en el primer mensaje del grupo) | Esquina de la colita |
|---|---|---|---|---|
| Paciente | izquierda | `--bubble-patient` (+ borde 1 px `--border` en claro) | ninguno (es el chat de esa persona) | arriba a la izquierda, 4 px |
| Asiri | derecha | `--bubble-asiri` | `RobotIcon` 16 + "Asiri" en `text-caption` 500 `bot.fg` | arriba a la derecha, 4 px |
| Persona de la clínica | derecha | `--bubble-staff` | `UserIcon` 16 + nombre ("Irina", "Dra. Raquel") en `text-caption` 500 `human.fg` | arriba a la derecha, 4 px |
| Sistema | centro | sin burbuja: pastilla `--surface-sunken`, radio `full` | ícono del evento 16 + texto `text-caption` `--text-2` | — |

- Ancho máximo: 80% mobile, 560 px escritorio. Padding 8 12. Radio `md` (16 px). Texto 16 px mobile / 15 px escritorio, `text-1`.
- Agrupado: mismo autor dentro de 2 minutos = mismo grupo (2 px entre burbujas, solo la primera lleva colita y rótulo). Entre grupos: 12 px.
- Meta: hora `text-caption` `tabular-nums` `--text-3` + tildes (16 px) abajo a la derecha, con el truco de `float` actual.
- **Mensajes de sistema** (ejemplos): "Asiri derivó al grupo: urgencia", "Irina tomó la conversación · Asiri vuelve 15:42", "Recordatorio de 24 h enviado", "Tipo cambiado a Proveedor por Irina", "Se agendó un turno para el jue 22/10 10:30" (con enlace a la tarjeta de turno).
- **Tarjeta de turno dentro del chat:** cuando Asiri agenda, confirma o cancela, debajo de la burbuja va la `AppointmentCard` compacta (§3.11).
- Separador de día: pastilla centrada, sticky arriba (z 10), "Hoy", "Ayer", "Lunes 12 de octubre".
- Estados: default · resaltada por búsqueda (anillo de 2 px `--focus`, coincidencias con fondo `attention.soft`) · atenuada (fuera del resultado de búsqueda: opacidad .45) · multimedia cargando (caja con tamaño reservado y fondo `--surface-sunken`, sin saltos de layout) · multimedia vencida (chip "Ya no está disponible") · error de envío (§3.9) · nota interna (si se implementa: fondo `attention.soft`, borde punteado, rótulo "Nota interna: solo la ve la clínica").

### 3.11 Tarjeta de turno (`AppointmentCard`)

```
┌────────────────────────────────────────────┐
│ ● Jue 22 oct · 10:30          [Confirmado] │
│   Control de ortodoncia · 30 min            │
│   Mateo Gómez (hijo)                        │
│   [Ver en agenda]          [Más acciones ⋯] │
└────────────────────────────────────────────┘
```

- Variantes: `full` (agenda, ficha) y `compact` (chat, Hoy: una línea con fecha, hora, tratamiento y estado).
- Fecha en `text-headline` `tabular-nums`, tratamiento `text-footnote` `--text-2`, paciente si el teléfono tiene varias fichas (familia). Marcador de estado por forma (§2.2.3) a la izquierda y `StatusChip` de turno a la derecha.
- Acciones (según el permiso y la fuente): "Ver en agenda" siempre. "Confirmar", "Reprogramar" o "Anular" solo donde el panel escribe (agenda propia en modo práctica, AGE-06), **siempre con confirmación** y con el texto "Esto no toca Dentalink" mientras sea práctica.
- Estados: default · hover (nivel 2) · pasado (opacidad del texto al `--text-2`, sin acciones) · anulado (borde punteado, texto tachado) · cargando (esqueleto de 3 líneas) · error (sin datos de la agenda: "No se pudo leer la agenda. Reintentar") · vacío (en la ficha: "Sin turnos. [Agendar]").

### 3.12 Toast (`Toast`)

- Se reutiliza el proveedor actual (`components/ui/toast.tsx`) con estos cambios: posición **abajo al centro** en mobile, por encima de la barra inferior (`bottom: 64px + safe-area + 12px`), y abajo a la derecha en escritorio. Fondo `--surface-raised`, nivel 3, radio `md`, ancho máximo 420 px, padding 12 16.
- Ícono 20 `fill` según el tipo (éxito `CheckCircleIcon` `payment.fg`, error `WarningCircleIcon` `urgent.fg`, info `InfoIcon` `human.fg`), texto `text-footnote` `--text-1`, y **acción opcional** a la derecha (`ghost` "Deshacer" o "Reintentar").
- Duración: 5 s con acción, 4 s sin acción, los errores no se van solos (se cierran con la X). Se pausa con el puntero encima o con foco. Tope de 3 visibles.
- Reemplaza los avisos propios de `conversation-list.tsx` ("Aplicando…", aviso masivo, aviso de error): todo pasa por `useToast()`.

### 3.13 Diálogo (`Dialog`) y confirmación (`ConfirmDialog`)

- Radix Dialog. Ancho 440 px escritorio. **En mobile, toda confirmación es una hoja** (§3.15), no un modal centrado.
- Trampa de foco, `Esc` cierra, el foco vuelve al disparador, `aria-labelledby` y `aria-describedby`.
- `ConfirmDialog`: título que dice la acción ("¿Anular el turno del jue 22/10 10:30?"), cuerpo con la consecuencia en una frase, botón de acción con el verbo exacto ("Sí, anular") y "Cancelar" `ghost`. Si es destructivo, el botón es `danger` y el foco inicial va a "Cancelar".

### 3.14 Menú y hoja de acciones (`DropdownMenu` / `ActionSheet`)

- Escritorio: Radix DropdownMenu, nivel 2, ítems de 36 px con ícono 20 y `Kbd` a la derecha. Se abre con clic, con clic derecho en las filas y con `.` sobre la fila enfocada.
- Mobile: hoja con ítems de 56 px, ícono 24, separadores entre grupos y "Cancelar" al final. Se abre con el botón `⋯` y con **mantener apretado** (500 ms, vibración corta con `navigator.vibrate(10)` si existe).
- Estados del ítem: default · hover/focus (fondo `--surface-sunken`) · deshabilitado con motivo en una segunda línea · destructivo (texto `urgent.fg`).

### 3.15 Hoja inferior mobile (`Sheet`)

- vaul (Drawer). Borde superior con radio `lg` (24 px), agarradera de 36 × 5 px `--border-strong` centrada a 8 px del borde, fondo `--surface-raised`, nivel 3, velo `--overlay`.
- Alturas (`snapPoints`): **media** (50% del alto) y **completa** (100% − 24 px arriba). Las hojas de confirmación solo tienen la altura de su contenido.
- Cierra arrastrando hacia abajo, tocando el velo o con "Cancelar". Trampa de foco y devolución del foco como el diálogo. Pie fijo con las acciones, por encima del `safe-area`.
- En escritorio el mismo componente se renderiza como **panel lateral derecho** de 420 px (para las fichas) o como `Dialog` (para las confirmaciones).
- Estados: cerrada · abriendo (320 ms) · media · completa · arrastrando · cargando (esqueleto adentro, la hoja ya abierta) · error (estado de error adentro, con "Reintentar").

### 3.16 Barra de navegación inferior mobile (`TabBar`)

```
┌──────────────────────────────────────────────────┐
│  [Tray•3]   [Chats•12]  [Calendar]  [Book]  [⋯]  │  64 px + safe-area
│  Atención    Chats       Agenda    Contactos Más │
└──────────────────────────────────────────────────┘
```

- 5 destinos fijos: **Atención** (`/atencion`), **Chats** (`/conversaciones`), **Agenda** (`/agenda`), **Contactos** (`/contactos`), **Más** (hoja con el resto). Quedan los cinco desde la etapa 7; antes, cada destino aparece cuando existe su pantalla (etapa 3, "Destinos que todavía no existen").
- Fondo `--surface`, borde superior `--border`, alto 64 px + `env(safe-area-inset-bottom)`. Cada destino ocupa 1/5 del ancho (≥ 72 px a 360) y todo el alto: ícono 24 + rótulo `text-caption` 500 (el rótulo nunca se oculta).
- Activo: ícono `fill` y rótulo en `--primary-text`, más una pastilla de 56 × 32 px `--primary-soft` detrás del ícono. Inactivo: ícono `regular` `--text-2`.
- Badges: Atención = cantidad de casos abiertos con fondo `urgent.solid` si hay alguna urgencia y `--primary` si no. Chats = conversaciones no leídas (`--primary`). Mínimo 18 × 18 px, `text-caption` 600, arriba a la derecha del ícono, con borde de 2 px `--surface`.
- Tocar el destino activo hace scroll arriba y, si ya está arriba, enfoca la búsqueda.
- Se oculta dentro de un chat abierto (el composer ocupa ese lugar) y con el teclado abierto.
- "Más" abre una hoja con: Hoy, Seguimientos, Recorrido, Recordatorios, Conocimiento, El agente, Servicios, Aprendizaje, Estado, Configuración, Instalar la app (si no está instalada), Tema y Avisos de urgencias (estos dos, hasta que exista Configuración en la etapa 12), Cerrar sesión.

### 3.17 Esqueletos (`Skeleton`)

- Bloques `--surface-sunken`, radio `xs` (texto) o `full` (avatar). Pulso de opacidad de 1 a .55 en 1,2 s (se desactiva con reduced-motion).
- Cada ruta tiene su `loading.tsx` con la **forma real** de la pantalla (no el genérico de hoy):
  - Fila de chat: avatar + 2 líneas (60% y 85%) + hora. Se muestran 8.
  - Chat: header real (el nombre ya se conoce desde la lista) + 5 burbujas alternadas de anchos 40/65/30/55/45%.
  - Atención: 2 encabezados de grupo + 3 tarjetas de 96 px.
  - Hoy: estado + 3 tarjetas + lista de 4 turnos.
  - Agenda día: columna de horas real + 3 bloques.
- Se muestran solo si la carga pasa de 300 ms (para no parpadear) y tienen `aria-busy="true"` con "Cargando…" para lectores de pantalla.

### 3.18 Estado vacío y de error (`EmptyState`, `ErrorState`)

Se mantienen los actuales (`components/ui/estado.tsx`) con: ícono `duotone` 48 en `--text-3` sin la caja de color, título `text-title-3`, descripción `text-footnote` `--text-2` de máximo 2 líneas, y **siempre una acción** o una explicación de por qué no hay. Los textos son específicos ("No hay urgencias abiertas. Asiri avisa acá apenas llegue una.") y no genéricos.

### 3.19 Otros (de DIS-07)

`Switch` (track 44 × 26, pulgar 22, encendido `--primary`, con rótulo visible al lado; nunca switch suelto), `Checkbox` (20 px, borde `--border-strong`, radio `xs`), `Tooltip` (solo complementario: nunca el único lugar de una información; se abre con hover o foco después de 500 ms, no existe en táctil), `Kbd` (`text-caption` `tabular-nums`, borde `--border`, radio `xs`, padding 0 6), `CommandPalette` (cmdk, `Cmd/Ctrl+K`, 560 px, buscar contactos, ir a pantallas y acciones del chat abierto).

---

## 4. Rediseño por pantalla

Cada pantalla tiene su versión **Escritorio (1440)** y **Mobile (390)**. Los wireframes son de estructura (no de pixel). Los textos de ejemplo usan datos inventados (los del modo demo, §5 etapa 0).

### 4.0 Estructura y navegación

**Rutas nuevas:** `/hoy` (reemplaza a `/dashboard`, que redirige), `/atencion`, `/contactos`, `/contactos/[id]`, `/contactos/por-clasificar`, `/contactos/silenciados`, `/agenda` (reemplaza a `/citas`, que redirige), `/recorrido`, `/seguimientos`, `/estado` (reemplaza a `/control`, que redirige), `/configuracion`. Se mantienen `/conversaciones`, `/recordatorios`, `/conocimiento`, `/agente`, `/servicios`, `/aprendizaje`.

**Inicio por rol:** secretaria → `/atencion` · Dra. → `/hoy` · admin (Lucas) → `/hoy`. Es el `start_url` del manifest de la PWA (`/atencion`) y la redirección de `/`. Mientras una de esas pantallas no existe, el inicio va a la ruta actual (etapa 3).

**Escritorio (≥ 1024): barra lateral agrupada de 240 px** (colapsable a 64 px con `[`; se recuerda en `localStorage` con try/catch).

```
┌──────────────────────┐
│ (logo) Áurea          │  ← marca: logo de la clínica + "Dra. Raquel" en --brand
│ [● Asiri atendiendo]  │  ← pastilla de estado global (abre Estado)
│ [⌕ Buscar…    Ctrl K] │
│                       │
│ Trabajo               │  ← rótulo de grupo: text-caption 500 --text-3, sin mayúsculas
│  ☀ Hoy                │
│  ▣ Atención       3   │  ← contador; rojo (urgent.solid) si hay urgencia
│  💬 Conversaciones 12  │
│  ▦ Agenda             │
│  ☰ Contactos          │
│  ✈ Seguimientos   5   │
│ Crecimiento           │
│  ⏷ Recorrido          │
│ Asiri                 │
│  🤖 El agente          │
│  📖 Conocimiento       │
│  🏷 Servicios          │
│  💡 Aprendizaje        │
│  🔔 Recordatorios      │
│ Sistema               │
│  〰 Estado             │
│  ⚙ Configuración      │
│ ───────────────────── │
│ (AV) Irina · Secretaria│  ← menú de cuenta: tema, cerrar sesión
└──────────────────────┘
```
(Los símbolos del wireframe representan los íconos Phosphor de §2.5.)

- Ítem: alto 36 px, radio `sm`, ícono 20, `text-callout`. Activo: fondo `--primary-soft`, texto `--primary-text`, ícono `fill`. Hover: `--surface-sunken`.
- Colapsada: solo íconos con `aria-label` y tooltip, contadores como punto con número.

**Tablet (768-1023): rail de 72 px** con los 5 destinos de la barra inferior más "Más", ícono 24 + rótulo `text-caption` debajo.

**Mobile (< 768):** header de 56 px por pantalla (título `text-title-3` siempre a la izquierda, en iOS y en Android; acciones a la derecha) + barra inferior (§3.16). En las pantallas de lista el título grande (`text-title-2`) está en el contenido y se achica al header al hacer scroll (como iOS).

**Pastilla "Asiri apagada"** (reemplaza el banner rojo con emoji): si el bot está apagado globalmente, en mobile aparece una pastilla fija arriba (debajo del header, z 65) con fondo `attention.soft`, borde 1 px `attention.fg` y texto `attention.fg` 600: "Asiri está apagada · los pacientes no reciben respuesta". Tocarla abre una hoja con la explicación, quién la apagó y cuándo, y el botón "Prender Asiri" (solo admin, con confirmación). En escritorio la pastilla de la barra lateral cambia a ese estado y aparece además una franja de 40 px arriba del contenido.

**Paleta de comandos** (escritorio): `Ctrl/Cmd+K`. Atajos globales: `G` luego `H` (Hoy), `G A` (Atención), `G C` (Conversaciones), `G G` (Agenda), `G K` (Contactos). Se listan en Configuración → Atajos y en `?`.

### 4.1 Conversaciones (inbox + chat)

**Escritorio 1440:**

```
┌sidebar 240┬─ lista 360 ─────────────────┬─ chat (flex ≈ 500) ───────────────────────┬─ rail 340 ──────────────┐
│           │ Conversaciones   ● En vivo   │ (AV) Mariela Gómez · Familiar              │ (AV72)                  │
│           │ [⌕ Buscar nombre o teléfono] │      [Persona · Irina · 42 min] [Devolver] │ Mariela Gómez           │
│           │ [Todos 312][No leídos 12]    │────────────────────────────────────────────│ Familiar · 2 fichas     │
│           │ [Personas 3][Silenciados 21] │ [Urgencia] Dolor · hace 3 min [Tomar][✓]  │ [Asiri][Persona]        │
│           │ [Por clasificar 8]           │────────────────────────────────────────────│ Turnos                  │
│           │──────────────────────────────│            ─ Hoy ─                         │  ● Jue 22/10 10:30 Mateo│
│           │ ▌(AV) Mariela Gómez   14:32  │ [paciente] Mi hijo tiene el aparato…       │ Recorrido               │
│           │       [Urgencia] Le duele (3)│              [Asiri] Entiendo. Ya le aviso │  ●─●─○─○ En tratamiento │
│           │ (AV) Carlos Pérez     14:10  │              a la clínica…                 │ Notas                   │
│           │       Asiri: Te espero el…   │   · Asiri derivó al grupo: urgencia ·      │  + Agregar nota         │
│           │ (AV) Lab. Dental Norte 13:55 │              [Irina] Hola Mariela, …       │ Tipo de contacto        │
│           │       [Silenciado] Llegó el… │────────────────────────────────────────────│  [Familiar ▾]           │
│           │ …                            │ [⚡][ Escribí un mensaje…          ][📎][➤]│ [Ver ficha completa]    │
└───────────┴──────────────────────────────┴────────────────────────────────────────────┴─────────────────────────┘
```

- **Lista (360 px):** título + indicador "En vivo" (punto + texto, como hoy), búsqueda (nombre, alias, teléfono; resultado en < 300 ms; `/` enfoca), chips de filtro con contador: Todos · No leídos · Personas (modo humano) · Silenciados · Por clasificar. Debajo, solo si hay chats en modo persona, el botón `secondary` `sm` "Devolver todos a Asiri (3)" con confirmación (comportamiento actual).
- Orden por último mensaje. Lista virtualizada (`@tanstack/react-virtual`) con filas de 60 px.
- **Chat:** header (§3.8), franja de caso abierto si existe, línea de tiempo (§3.10), composer (§3.9). Buscar dentro del chat: barra debajo del header con "3 de 12" y flechas (`Enter` / `Shift+Enter`).
- **Rail de contexto (340 px):** se muestra por defecto a ≥ 1440 y se alterna con `]`. Entre 1024 y 1439 es un panel que se superpone. Contenido: la ficha resumida (§4.2: identidad, tipo, familia, próximos turnos, etapa del recorrido, notas y "Ver ficha completa").
- **Teclado (Superhuman):** `J/K` siguiente o anterior conversación, `Enter` abrir, `Esc` volver a la lista, `U` marcar no leído, `H` atender yo, `B` devolver a Asiri, `T` cambiar tipo, `/` buscar, `R` enfocar el composer.
- **Menú de fila** (clic derecho, `.` o botón `⋯` que aparece en hover): Abrir, Marcar leído / no leído, Atender yo / Devolver a Asiri, Cambiar tipo…, Ver ficha.

**Mobile 390:**

```
Lista (/conversaciones)                    Chat (/conversaciones/[id]) — pantalla completa, empujada
┌──────────────────────────────────┐       ┌──────────────────────────────────┐
│ Chats                  ● En vivo │ 56    │ ‹ (AV) Mariela Gómez     (⌕)(⋯)  │ 56
│ [⌕ Buscar nombre o teléfono     ]│       │       [Persona · vuelve en 42 min]│
│ [Todos][No leídos 12][Personas 3]│→scroll│ [Urgencia] Dolor · 3 min [Tomar] │ 40
│──────────────────────────────────│       │──────────────────────────────────│
│ (AV48) Mariela Gómez       14:32 │ 72    │            ─ Hoy ─                │
│        [Urgencia] Le duele…  (3) │       │ ┌─────────────────────┐           │
│ (AV48) Carlos Pérez        14:10 │       │ │Mi hijo tiene el     │           │
│        Asiri: Te espero el jue…  │       │ │aparato salido 14:30 │           │
│ (AV48) Lab. Dental Norte   13:55 │       │ └─────────────────────┘           │
│        [Silenciado] Llegó el…    │       │          ┌──────────────────────┐ │
│ …                                │       │          │ Asiri                │ │
│                                  │       │          │ Entiendo. Ya le aviso│ │
│──────────────────────────────────│       │          └──────────────────────┘ │
│ Atención Chats Agenda Contac. Más│ 64+sa │ [⚡][Escribí un mensaje…  ][📎][➤]│ composer
└──────────────────────────────────┘       └──────────────────────────────────┘
```

- La lista ocupa toda la pantalla. El chat se abre **empujado** desde la derecha (320 ms, con View Transitions de Next si está disponible; si no, sin animación) y la barra inferior se oculta. "Atrás" y el gesto de borde vuelven a la lista **manteniendo el scroll**.
- La timeline ocupa al menos el 65% del alto con el teclado cerrado (criterio de ATE-05).
- El header del chat abre la **hoja de contexto** (media altura: tipo, estado, próximos turnos; completa: la ficha entera).
- **Gestos en la fila** (MOB-03), con umbral del 30% del ancho:
  - **Deslizar a la derecha** → "Leído" / "No leído" (fondo `--primary`, `EnvelopeSimpleOpenIcon` 24 blanco). Se completa con un toast "Marcado como leído · Deshacer".
  - **Deslizar a la izquierda** → revela dos acciones de 80 px: **"Tipo"** (fondo `--surface-sunken`, `TagIcon`; abre la hoja de tipo de contacto) y **"Persona" / "Asiri"** (fondo `human.solid` o `bot.solid`, cambia el modo con toast + Deshacer). Deslizar más del 60% ejecuta la última sin soltar.
  - **Mantener apretado** → hoja de acciones con todo lo anterior + Ver ficha.
  - **Cada gesto tiene su equivalente:** el botón `⋯` del header del chat y la hoja de mantener apretado. Los gestos tienen `aria-hidden` y las acciones están en el menú accesible.
- Tirar hacia abajo en la lista = forzar el refetch (indicador nativo de 48 px).

### 4.2 Ficha de contacto (nueva) — `/contactos/[id]`

Una "persona" = un **teléfono** (es la unidad del chat) con sus fichas de paciente vinculadas (familia). **Regla de datos:** sin DNI, dirección ni email en el render hasta que esté el contrato (SEG-17, CRM-07).

**Escritorio 1440** (página propia; también se abre como panel lateral de 420 px desde cualquier lista):

```
┌sidebar┬────────────────────────────────────────────────────────────────────────────────────────┐
│       │ ‹ Contactos                                                                            │
│       │ (AV72) Mariela Gómez                          [Abrir chat] [Agendar] [⋯]               │
│       │        +54 9 388 000-1234 · Familiar · [Asiri atiende]                                 │
│       │        Tipo puesto por Irina el 21/10 · motivo: mamá de paciente                       │
│       │────────────────────────────────────────────────────────────────────────────────────────│
│       │ ┌ Columna principal 720 ─────────────────────────────┐ ┌ Columna lateral 340 ───────┐ │
│       │ │ Recorrido                                          │ │ Familia                    │ │
│       │ │  Consulta ── Primera consulta ── Devolución ── En tratamiento ●                    │ │
│       │ │  (stepper; etapa actual en --primary, motivo si    │ │ (AV32) Mateo Gómez · hijo  │ │
│       │ │   se marcó a mano)                                 │ │ (AV32) Sofía Gómez · hija  │ │
│       │ │ Actividad                    [Todo][Turnos][Chat]  │ │ [+ Vincular ficha]         │ │
│       │ │  hoy 14:32  Urgencia derivada por Asiri            │ │ Próximos turnos            │ │
│       │ │  21/10      Tipo: Familiar (Irina)                 │ │  ● Jue 22/10 10:30 Mateo   │ │
│       │ │  15/10      Turno confirmado por recordatorio      │ │  ○ Mar 03/11 09:00 Sofía   │ │
│       │ │  02/10      Primera consulta (vino)                │ │ Turnos pasados (6) ›       │ │
│       │ │  …                                                 │ │ Notas                      │ │
│       │ └────────────────────────────────────────────────────┘ │  [Escribí una nota…]       │ │
│       │                                                        │  "Prefiere turnos a la     │ │
│       │                                                        │   tarde" · Irina 12/10     │ │
│       │                                                        │ Seguimiento                │ │
│       │                                                        │  Ninguno pendiente         │ │
│       │                                                        └────────────────────────────┘ │
└───────┴────────────────────────────────────────────────────────────────────────────────────────┘
```

**Mobile 390** (pantalla completa empujada; desde el chat, hoja de contexto en dos alturas):

```
┌──────────────────────────────────┐
│ ‹ Contactos               (⋯)    │ 56
│        (AV72)                    │
│     Mariela Gómez                │ title-1
│  +54 9 388 000-1234              │
│  [Familiar] [Asiri atiende]      │
│ [Chat] [Llamar] [Agendar]        │ 3 botones de 48 px, iguales
│──────────────────────────────────│
│ [Resumen][Turnos][Actividad][Notas] ← segmented, sticky bajo el header
│ Recorrido                        │
│  ●──●──●──○  En tratamiento      │ stepper horizontal compacto
│ Familia                          │
│  (AV) Mateo · hijo           ›   │ 56 px por fila
│  (AV) Sofía · hija           ›   │
│ Próximo turno                    │
│  [AppointmentCard compact]       │
│ Tipo de contacto                 │
│  Familiar · Irina 21/10      ›   │ abre la hoja de tipo
└──────────────────────────────────┘
```

- **Jerarquía:** identidad y estado → acciones (chat, agendar) → recorrido → familia → turnos → actividad → notas.
- **Agendar:** mientras la agenda sea la de Dentalink, abre Dentalink (el panel no escribe ahí). En modo práctica (AGE-06) abre la hoja de turno nuevo con vista previa, la franja "Esto no toca Dentalink" y la confirmación explícita. Ningún botón escribe en la agenda con un solo toque (regla del 15/10).
- **Tipo de contacto** (CRM-03): fila que abre una hoja con las opciones y su consecuencia, más **motivo obligatorio** de una lista corta (Mamá/papá de paciente, Proveedor de insumos, Laboratorio, Colega, Spam/empresa, Conocido, Otro + nota). Si el contacto tiene turnos y se lo silencia: confirmación doble ("Tiene 2 turnos en la agenda. ¿Igual no es paciente?"). La leyenda muestra autor y fecha. "Equipo" solo aparece para admin.
- **Familia** (CRM-08): chips de relación (tutor, hijo/a, pareja, duplicado, sin definir). "Sin definir" lleva un botón "Confirmar relación" con autor.
- **Actividad:** línea de tiempo con hechos de la base (mensajes resumidos por día, turnos, cambios de tipo, derivaciones, recordatorios y seguimientos), con autor (Asiri, persona o sistema) e ícono por tipo.
- **Notas:** texto libre, con autor y fecha, editables solo por su autor.
- **Estados:** cargando (esqueleto de cabecera + 3 secciones) · sin chat (contacto solo de la agenda: el botón "Chat" pasa a "Escribir por WhatsApp" y aclara que abre una conversación nueva) · sin ficha (prospecto: el recorrido arranca en "Consulta" y aparece "Crear ficha" deshabilitado con la explicación "La ficha se crea en Dentalink al agendar") · error parcial (si Dentalink no responde, solo la sección de turnos muestra el error, el resto se ve).

### 4.3 Bandeja de Atención (nueva) — `/atencion`

Es la pantalla principal de la secretaria: reemplaza al grupo de WhatsApp como lugar de trabajo. Un **caso** = un motivo abierto para un contacto (urgencia, pago, pidió persona, Asiri no supo, por clasificar), con dueño y estado.

**Grupos fijos y orden:** Urgencias → Requiere secretaria (pagos, pidió persona, consulta que Asiri derivó) → En curso (tomados por alguien) → Esperando al paciente → Resueltas hoy (colapsado).

**Mobile 390:**

```
┌──────────────────────────────────┐
│ Atención                (filtro) │ 56
│ [Todos 6][Míos 2][Sin dueño 4]   │
│──────────────────────────────────│
│ Urgencias · 1                    │ encabezado sticky, urgent.fg + ícono
│ ┌──────────────────────────────┐ │
│ ▌[Urgencia] hace 3 min          │ │ barra de 4 px urgent.fg (+ ícono: se ve sin color)
│ │ Mariela Gómez · Familiar      │ │
│ │ "Se le salió el aparato a mi  │ │ motivo en lenguaje llano (lo que registró el bot)
│ │  hijo y le duele"             │ │
│ │ Asiri ya respondió y derivó   │ │ text-footnote --text-2
│ │ [Abrir chat]      [Tomar] ←48 │ │
│ └──────────────────────────────┘ │
│ Requiere secretaria · 3          │
│ ┌──────────────────────────────┐ │
│ │[Pago] 14:05 · Carlos Pérez    │ │
│ │ Mandó un comprobante          │ │
│ │ [Abrir chat]      [Tomar]     │ │
│ └──────────────────────────────┘ │
│ En curso · 2                     │
│ ┌──────────────────────────────┐ │
│ │[Persona · Irina] Ana López    │ │
│ │ Asiri vuelve en 42 min        │ │
│ │ [Esperando paciente][Resolver]│ │
│ └──────────────────────────────┘ │
│ Resueltas hoy · 7            ›   │
│──────────────────────────────────│
│ Atención Chats Agenda Contac. Más│
└──────────────────────────────────┘
```

- **Tarjeta (96-140 px):** `StatusChip` del motivo + hora relativa (`tabular-nums`, se actualiza cada minuto), nombre + tipo, motivo en lenguaje llano (máx. 2 líneas), contexto ("Asiri ya respondió y derivó", "Tiene turno mañana 10:30"), contador si el motivo se repitió ("×3"), dueño (avatar 24 + nombre) si está tomado, y como mucho **dos botones** de 48 px: el principal a la derecha.
- **Acciones por estado:** sin dueño → "Abrir chat" + **"Tomar"** (asigna a mí, pasa a "En curso" y pone el chat en modo persona) · en curso → "Esperando paciente" + **"Resolver"** · esperando → "Resolver". "Resolver" abre una hoja corta: nota opcional (textarea) + casilla "Devolver a Asiri" **tildada por defecto** + "Resolver". Todo con toast + Deshacer.
- **Gestos:** deslizar a la derecha = Tomar o Resolver (según el estado), a la izquierda = Esperando paciente. Con botón equivalente siempre.
- **La urgencia se distingue sin color:** ícono `FirstAidKitIcon`, el texto "Urgencia", el grupo propio arriba de todo y la barra izquierda.
- **Vacío:** "Todo al día. Cuando Asiri derive algo, aparece acá." con `TrayIcon` duotone. **Error:** banner arriba "No se pudo actualizar la bandeja. Lo que ves puede estar desactualizado · Reintentar" (no se borra la lista).
- **Tiempo real:** las tarjetas nuevas entran con `--dur-base` arriba de su grupo y el badge de la barra inferior se actualiza. Notificación push solo para Urgencia y Requiere secretaria (MOB-04), sin datos clínicos en el texto ("Hay una urgencia nueva en Atención").

**Escritorio 1440 (lista + detalle, Linear Inbox):**

```
┌sidebar┬─ bandeja 420 ─────────────────────────┬─ detalle (flex) ─────────────────────────────────────┐
│       │ Atención                [Todos][Míos] │ [Urgencia] Mariela Gómez · Familiar · hace 3 min     │
│       │ Urgencias · 1                         │ [Tomar  T]  [Esperando paciente  W]  [Resolver  E]   │
│       │ ▌● Mariela Gómez   Urgencia    3 min  │──────────────────────────────────────────────────────│
│       │ Requiere secretaria · 3               │ Motivo: "Se le salió el aparato a mi hijo y le duele"│
│       │  $ Carlos Pérez    Pago        14:05  │ Lo que hizo Asiri: respondió y derivó al grupo 14:29 │
│       │  ✋ Ana Ruiz        Pidió persona 13:50│ Próximo turno: jue 22/10 10:30 (Mateo)               │
│       │ En curso · 2                          │──────────────────────────────────────────────────────│
│       │  (AV) Ana López    Irina      42 min  │ [chat embebido: últimos mensajes + composer]         │
│       │ Esperando al paciente · 0             │                                                      │
│       │ Resueltas hoy · 7 ›                   │                                                      │
└───────┴───────────────────────────────────────┴──────────────────────────────────────────────────────┘
```

- Filas de 44 px en la bandeja (una línea: ícono de estado, nombre, motivo corto, dueño o tiempo). `J/K` para moverse, `T` tomar, `W` esperando, `E` resolver; al resolver, el foco salta al siguiente (Superhuman).
- El detalle embebe el chat (mismos módulos de §4.1) para contestar sin cambiar de pantalla. Como la bandeja (etapa 6) sale antes que los módulos del chat (etapa 5), hasta la etapa 5 el detalle muestra los últimos mensajes en solo lectura y "Abrir chat".

### 4.4 Hoy (dashboard) — `/hoy`

Pregunta que responde en 10 segundos: **"¿Asiri está bien, qué hay que hacer y qué turnos hay?"**. Reemplaza las 7 tarjetas de KPI iguales.

**Mobile 390** (el bloque Hoy entra **sin scroll**: criterio de ATE-07):

```
┌──────────────────────────────────┐
│ Hoy                       (AV)   │ 56
│ Buen día, Raquel                 │ title-1
│ Lunes 19 de octubre              │ footnote --text-2
│ ┌──────────────────────────────┐ │
│ │ ● Asiri atendiendo            │ │ estado global: bot.fg; si hay falla, attention/urgent
│ │   WhatsApp conectado · último │ │
│ │   mensaje hace 1 min          │ │
│ └──────────────────────────────┘ │
│ ┌─────────┐┌─────────┐┌────────┐ │
│ │ 1       ││ 3       ││ 8      │ │ display tabular
│ │Urgencia ││Para la  ││Turnos  │ │
│ │abierta  ││secretaria││mañana │ │ cada una abre su pantalla
│ └─────────┘└─────────┘└────────┘ │
│ Turnos de hoy · 6           Ver ›│
│  09:00 ● Mateo Gómez  Control    │ lista compacta, tabular
│  09:30 ○ Ana Ruiz     Consulta   │
│  10:30 ● Sofía Díaz   Control    │
│──────────────────────────────────│
│ (debajo del pliegue)             │
│ Esta semana                      │
│  Asiri agendó 14 turnos ▁▃▅▂▆▇▄  │ 3 KPIs con sparkline + frase
│  Respondió 312 mensajes          │
│  Confirmaron 41 de 46 (89%)      │
└──────────────────────────────────┘
```

**Escritorio 1440:**

```
┌sidebar┬──────────────────────────────────────────────────────────────────────────────────────────┐
│       │ Buen día, Raquel · Lunes 19 de octubre                         [● Asiri atendiendo]      │
│       │ ┌ Urgencias 1 ┐ ┌ Secretaria 3 ┐ ┌ Esperan a una persona 2 ┐ ┌ Turnos mañana 8 ┐        │
│       │ ┌ Turnos de hoy (6) ───────────────────────┐ ┌ Atención: lo abierto ─────────────────┐ │
│       │ │ 09:00 ● Mateo Gómez   Control    Conf.   │ │ [Urgencia] Mariela G. · 3 min  Tomar  │ │
│       │ │ 09:30 ○ Ana Ruiz      Consulta   Sin conf│ │ [Pago] Carlos P. · 14:05       Tomar  │ │
│       │ │ …                                        │ │ …                                     │ │
│       │ └──────────────────────────────────────────┘ └───────────────────────────────────────┘ │
│       │ Esta semana  [7 días][30 días]                                                         │
│       │ ┌ Turnos que agendó Asiri ┐ ┌ Mensajes respondidos ┐ ┌ Confirmaciones ┐                │
│       │ │ 14  ▲ 3 vs semana pasada │ │ 312                  │ │ 89% (41/46)    │                │
│       │ │ ▁▃▅▂▆▇▄                  │ │ ▃▄▅▅▆▄▃              │ │ ▆▇▇▆▇█▇        │                │
│       │ └─────────────────────────┘ └──────────────────────┘ └────────────────┘                │
│       │ Mensajes por día (gráfico de barras con eje, leyenda y tabla accesible "Ver datos")     │
└───────┴──────────────────────────────────────────────────────────────────────────────────────────┘
```

- Gráficos con la skill **dataviz**: barras con eje Y visible, 2 series máximo (paciente / Asiri) en `--text-3` y `--primary`, tooltip con valores, y tabla alternativa accesible.
- KPIs con `text-display` `tabular-nums`, variación con flecha **y** texto ("3 más que la semana pasada"), nunca solo color.
- **Estados:** sin datos de Dentalink → la tarjeta de turnos dice "No se pudo leer la agenda" y el resto se ve · Asiri apagada → la tarjeta de estado pasa a `attention` con "Prender" (admin) · primer día de la semana sin datos → "Todavía no hay datos de esta semana".

### 4.5 Agenda — `/agenda` (hoy citas)

Hoy: grilla mensual de 7 columnas a 11 px, de solo lectura desde Dentalink (≤ 400 citas). Nuevo: **día** en mobile y **semana** en escritorio, con huecos visibles. Fuente: Dentalink por rango (AGE-01) ahora, el espejo (AGE-03) y la agenda propia en sombra (AGE-05/06) después, **con el mismo adaptador** (`lib/agenda/fuente.ts`).

**Mobile 390 — Día:**

```
┌──────────────────────────────────┐
│ Agenda        [Hoy]  (⌕) (+)     │ 56   (+ solo en modo práctica)
│ Octubre 2026                     │
│ [L19][M20][M21][J22][V23][S24]…  │ tira de días, scroll horizontal interno, hoy marcado
│  ·    ··   ·    ···  ··          │ puntos = cantidad de turnos
│──────────────────────────────────│
│ 08:00 ─────────────────────────  │
│ 08:30  ┌ Libre · 30 min ───────┐ │ hueco: borde punteado --border-strong, texto --text-3
│ 09:00  ● Mateo Gómez  Control   │ │ bloque: alto proporcional (10 min = 16 px)
│        Confirmado               │ │
│ 09:30  ○ Ana Ruiz  Consulta     │ │
│        Sin confirmar            │ │
│ 10:00  ┄ Lucía Paz (anulado) ┄  │ │
│ 13:00 ─── Cerrado 13 a 16 ───── │ franja rayada --surface-sunken
│ ── ahora 14:32 ──────────────── │ línea primary con punto
│──────────────────────────────────│
│ Atención Chats Agenda Contac. Más│
└──────────────────────────────────┘
```

- Tocar un turno abre la **hoja de detalle**: paciente (con enlace a la ficha y al chat), tratamiento, profesional, estado con historial, recordatorios enviados, y acciones según la fuente. Con Dentalink: solo lectura, con "Abrir en Dentalink". En modo práctica (AGE-06): Confirmar, Reprogramar, Anular, todas con confirmación y la franja fija "Modo práctica: esto no toca Dentalink" en `attention`.
- Deslizar horizontalmente sobre la grilla cambia de día. "Hoy" vuelve al día actual.
- **Leyenda** abajo de todo, en grises legible (forma + texto).

**Escritorio 1440 — Semana:**

```
┌sidebar┬──────────────────────────────────────────────────────────────────────────────────────────┐
│       │ Agenda  ‹ 19 – 24 oct 2026 ›  [Hoy]   [Día][Semana][Mes]   Fuente: Dentalink (lectura)    │
│       │       │ Lun 19  │ Mar 20  │ Mié 21  │ Jue 22  │ Vie 23  │ Sáb 24                         │
│       │ 08:00 │         │         │         │         │         │                                │
│       │ 09:00 │● Mateo  │○ Ana    │         │● Sofía  │         │                                │
│       │ 09:30 │ Control │ Consulta│ (libre) │ Control │         │                                │
│       │ …     │         │         │         │         │         │                                │
│       │ 13:00 │░░░ cerrado ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│                                │
│       │──────────────────────────────────────────────────────────────── panel de detalle 420 → │
└───────┴──────────────────────────────────────────────────────────────────────────────────────────┘
```

- Columnas por día con las franjas reales de atención (de `horarios_core`), huecos libres visibles, bloques con nombre + tratamiento + marcador de estado. Clic → panel lateral de detalle (el mismo contenido que la hoja mobile). La vista Mes se mantiene como resumen (puntos por día, sin nombres).
- **Estados:** cargando (columnas con esqueleto) · error de Dentalink (banner con "Reintentar"; la última semana cargada queda visible y marcada "desactualizada") · día sin turnos ("Sin turnos este día") · feriado o cierre ("Cerrado: feriado", franja rayada).

### 4.6 Recordatorios — `/recordatorios`

**El workflow de Recordatorios no se toca.** Solo cambia la interfaz de la página que ya existe (prender/apagar, suspender un día, adelantar un día, vacaciones).

- **Mobile 390:** estado arriba ("Recordatorios activos · próximo envío mañana 9:00 · 12 turnos") con `Switch` con rótulo y confirmación al apagar. Debajo, lista de **envíos de hoy** (paciente, turno, 24 h o 72 h, estado: enviado / confirmó / canceló / sin respuesta, con `StatusChip`). Las acciones de excepción (Suspender un día, Adelantar, Vacaciones) son filas de 56 px que abren cada una su hoja con el formulario y la vista previa del efecto ("No se van a mandar los recordatorios del vie 23/10: 9 turnos").
- **Escritorio 1440:** dos columnas: a la izquierda el estado + la tabla de envíos (fecha, paciente, turno, tipo, estado, `tabular-nums`), y a la derecha las tarjetas de excepciones con su formulario en línea.
- **Estados:** apagados (tarjeta de estado en `attention` con "Prender") · sin turnos para recordar ("Mañana no hay turnos para recordar") · error del servicio (banner y los controles deshabilitados con el motivo).

### 4.7 Conocimiento — `/conocimiento`

- **Escritorio 1440:** lista de secciones a la izquierda (280 px: Precios, Horarios, Dirección, Formas de pago, Tratamientos, Preguntas frecuentes) y editor a la derecha con ancho de lectura de 68 caracteres, vista previa de "cómo lo diría Asiri" y botón "Guardar" con confirmación. La guarda de precios se ve: "Solo se informa el precio de la consulta" (BOT-04). Guardar un texto con el monto de la cuota o del retenedor da un error claro y no se guarda (es una validación de datos, no de intención).
- **Mobile 390:** lista de secciones (filas de 56 px con la fecha de la última edición y su autor) → pantalla de edición empujada con textarea de 16 px y "Guardar" fijo abajo.
- **Estados:** sin guardar (pastilla "Cambios sin guardar" y confirmación al salir) · guardando · guardado (toast) · error · solo lectura (no admin: texto visible "Solo un admin puede editar").

### 4.8 Recorrido del paciente y embudo (nuevo) — `/recorrido`

Etapas (REC-02): **Consulta** (escribió) → **Primera consulta** (agendó / vino) → **Devolución / presupuesto** → **En tratamiento**, más **Dormido** y **Perdido** (este, con motivo obligatorio). Avanzan solo con hechos (REC-01); marcar a mano exige motivo y manda solo hasta el próximo hecho. `no_es_paciente` está excluido.

**Escritorio 1440 — Tablero:**

```
┌sidebar┬──────────────────────────────────────────────────────────────────────────────────────────┐
│       │ Recorrido   [Este mes][3 meses]   Origen: [Todos][Anuncios][Orgánico]     [Lista|Tablero]│
│       │ Consulta 48  →  Primera consulta 21 (44%)  →  Devolución 12 (57%)  →  En tratamiento 9   │
│       │ ┌ Consulta ───────┐┌ Primera consulta ┐┌ Devolución ─────┐┌ En tratamiento ┐┌ Dormidos ┐│
│       │ │ (AV) Ana Ruiz    ││ (AV) Mateo Gómez ││ (AV) Luis Vera   ││ (AV) Sofía D.   ││ …        ││
│       │ │ hace 2 d · anunc.││ vino 15/10       ││ presup. 10/10    ││ desde 09/2026   ││          ││
│       │ │ …                ││                  ││ sin respuesta 9 d││                 ││          ││
│       │ └──────────────────┘└──────────────────┘└──────────────────┘└─────────────────┘└──────────┘│
│       │ Motivos de pérdida: No respondió 7 · Precio 3 · Eligió otra clínica 2   [Editar motivos]  │
└───────┴──────────────────────────────────────────────────────────────────────────────────────────┘
```

- Arriba, la **franja del embudo** con conteos y conversión entre etapas (texto + número, `tabular-nums`). Columnas con tarjetas compactas (avatar 32, nombre, hecho más reciente, días en la etapa, origen). Clic en una tarjeta abre la ficha en el panel lateral (§4.2). **No hay arrastrar entre columnas**: mover de etapa a mano se hace desde la ficha con motivo (las etapas salen de hechos).
- **Mobile 390 — Lista:** la franja del embudo como 5 filas (etapa · conteo · % de la anterior) y, al tocar una etapa, la lista de personas de esa etapa (filas de 72 px) → ficha.
- **Estados:** sin datos todavía (antes de REC-01 en vivo: "El recorrido se arma con lo que registra Asiri. Arranca con el piloto del v7.", con los datos demo en el modo demo) · cálculo desactualizado (sello "actualizado hace 2 h") · error.

### 4.9 Seguimientos (nuevo) — `/seguimientos`

Reglas del producto (REC-04/05, D8): **de a uno**, con textos aprobados por la Dra., línea de baja incluida, tope diario visible, y **no existe "seleccionar todos"**. Las plantillas no llevan montos de cuota ni de retenedor (solo la consulta, decisión del 16/10). La baja la entiende Asiri con cualquier palabra: "respondé BAJA" es solo la instrucción visible (REC-04).

**Mobile 390:**

```
┌──────────────────────────────────┐
│ Seguimientos          Hoy 3 de 20│ 56  ← tope diario visible
│ [Consultó y no agendó 5][No vino 2][Presupuesto 3][Dormidos 9]
│──────────────────────────────────│
│ ┌──────────────────────────────┐ │
│ │ (AV) Ana Ruiz · Consulta      │ │ una tarjeta por vez (como Things/Tinder sin swipe ciego)
│ │ Escribió hace 4 días, no      │ │
│ │ agendó · vino por un anuncio  │ │
│ │ Mensaje (plantilla "Consulta  │ │
│ │ sin agendar"):                │ │
│ │ ┌──────────────────────────┐ │ │ vista previa COMPLETA, editable solo dentro
│ │ │Hola Ana, soy Asiri de la │ │ │ de lo que permite la plantilla
│ │ │clínica de la Dra. Raquel…│ │ │
│ │ │Si no querés recibir más  │ │ │ ← línea de baja siempre visible
│ │ │mensajes, respondé BAJA.  │ │ │
│ │ └──────────────────────────┘ │ │
│ │ [Descartar] [Posponer] [Enviar]│ │ Enviar = primary 48 px; Descartar pide motivo
│ └──────────────────────────────┘ │
│ Quedan 4 en esta cola            │
│──────────────────────────────────│
│ Atención Chats Agenda Contac. Más│
└──────────────────────────────────┘
```

- **Escritorio 1440:** a la izquierda la cola (lista de 360 px, filas de 60 px, filtro por tipo), al centro la persona elegida con el contexto (últimos 3 mensajes, turnos, etapa) y a la derecha la vista previa del mensaje con Enviar / Posponer / Descartar. Al enviar, pasa sola a la siguiente.
- "Enviar" abre una confirmación corta con el texto final y el número ("Se manda 1 mensaje a +54 9 388 …"). Toast con Deshacer de 5 s (el envío real sale después de los 5 s).
- **Estados:** tope alcanzado ("Llegaste al tope de hoy: 20 mensajes. Mañana se habilitan de nuevo", botones deshabilitados con ese texto) · contacto con baja (no aparece) · cola vacía ("No hay seguimientos pendientes de este tipo") · canal no habilitado (antes de REC-04: "Los seguimientos se habilitan cuando esté el contrato y el canal controlado", y la cola se ve en modo demo) · error de envío (la tarjeta vuelve con el motivo).

### 4.10 Configuración — `/configuracion` (y Estado — `/estado`)

**Configuración** (lista de secciones; mobile: filas de 56 px → pantalla empujada; escritorio: navegación lateral interna de 240 px + contenido de 640 px):
1. **Apariencia:** Claro / Oscuro / Sistema (`Segmented` con vista previa en miniatura). Hasta la etapa 12, el tema se elige en el menú de cuenta y en la hoja "Más".
2. **Notificaciones:** push de urgencias y de "requiere secretaria" (opt-in por usuario, con prueba "Mandarme una de prueba"). MOB-04 lo necesita desde el 02/12: hasta la etapa 12, este control vive en la hoja "Más".
3. **Instalar la app:** instrucciones por plataforma (Android: botón de instalar con `beforeinstallprompt`; iPhone: los 3 pasos con capturas).
4. **Equipo y permisos:** personas, rol (Admin / Secretaria / Doctora), quién puede marcar "Equipo", prender o apagar Asiri (SEG-12).
5. **Datos de la clínica:** dirección, horarios, alias bancario, grupo de derivaciones y admins del bot (cuando exista la tabla de BOT-11; antes, solo lectura con "Lo cambia Nexora").
6. **Atajos de teclado** (solo escritorio).
7. **Cuenta:** nombre, cerrar sesión.

**Estado** (SEG-15, reemplaza a Control): semáforo general arriba ("Todo funciona" / "Hay un problema" / "Asiri apagada") y filas para Asiri, WhatsApp (último mensaje que entró y que salió), Recordatorios, Health Check y monitor externo. Cada fila: `StatusChip`, la frase en lenguaje llano, y si hay un problema, "qué hacer" + el botón que lo repara (Reconectar). Prender o apagar Asiri: `Switch` con rótulo, confirmación con hoja y el nombre de quien lo tocó. Criterio: a 390 px cada escenario demo muestra el problema y la acción sin scroll.

**El agente, Servicios y Aprendizaje** mantienen su contenido y se migran a las primitivas y tokens (sin rediseño de estructura): encabezado de página con `text-title-2`, tarjetas de nivel 1, formularios con `Input`/`Textarea`, y el aviso de BOT-14 en El agente ("Atiende el v7: los prompts del v6 no se editan acá").

---

## 5. Plan de implementación por etapas

**Reglas para todas las etapas:**
- Rama por etapa en `nexora-whatsapp-agent`, PR con capturas. **Claude revisa las capturas contra el criterio común de abajo y despliega** en las fechas del backlog (C8 del backlog maestro). A Lucas le llegan como resultado. Las etapas cambian solo el panel: el backend de cada épica (tablas, n8n, v7) es un ítem propio del backlog, y el deploy sale por el camino de SEG-08, con la regla "una cosa a la vez" del backlog (§2).
- **El número de etapa es un nombre, no el orden.** El orden y las fechas son los del backlog maestro (§2), resumidos en la tabla del final de esta sección.
- Las pantallas nuevas se construyen **primero sobre el modo demo** (datos inventados) con un **adaptador por fuente** (`lib/fuentes/*.ts` con la misma interfaz para demo y real). Cuando el backend de la épica llega (casos, familias, eventos del recorrido, espejo de agenda), se cambia el adaptador y no la pantalla. Así el sistema propio avanza ya, como pidió Lucas.
- Las pruebas con datos reales (envíos, cambios de tipo) se hacen solo con el número de Lucas y con limpieza en el mismo turno (regla 9 del proyecto). Cero citas de prueba en Dentalink que queden vivas.
- **Criterio de listo común a todas las etapas** (además del propio):
  1. Capturas a **390** y **1440** (más 360 y 768), en claro y oscuro, generadas por el arnés, adjuntas al PR.
  2. **Sin scroll horizontal** en 360, 390, 768 y 1440 (`document.documentElement.scrollWidth <= innerWidth`, test de Playwright).
  3. **Contraste:** `scripts/contraste.mjs` pasa (≥ 4,5:1 texto, ≥ 3:1 bordes de control y foco) en los dos temas.
  4. **Lighthouse accesibilidad ≥ 95** en cada ruta tocada (mobile, modo demo) y **axe sin "serious" ni "critical"**.
  5. `pnpm typecheck` y `pnpm build` sin errores. Ningún texto < 12 px a 390 (test). Objetivos táctiles ≥ 44 × 44 en mobile (script).

### Etapa 0 — Base de verificación: modo demo y arnés de capturas (DIS-01) · 3 días
- **Archivos:** `lib/demo/fixtures.ts` (~40 contactos de todos los tipos, familias de 2-3 fichas, chats con multimedia, casos de Atención de cada motivo, turnos de 2 semanas, eventos de recorrido, colas de seguimiento), `lib/fuentes/{conversaciones,chat,contactos,casos,agenda,recorrido,seguimientos}.ts` (interfaz + implementación demo + real donde ya existe), `lib/demo/modo.ts` (`DEMO_MODE`, solo en dev local), `playwright.config.ts`, `tests/e2e/capturas.spec.ts`, `tests/e2e/sin-scroll.spec.ts`, `tests/e2e/a11y.spec.ts` (`@axe-core/playwright`), `scripts/contraste.mjs`, `scripts/lighthouse.mjs`, `package.json` (scripts `capturas`, `a11y`, `contraste`).
- **Listo cuando:** `pnpm capturas` genera 4+ capturas por ruta actual con `DEMO_MODE=1`, con 0 teléfonos reales y **ningún pedido de red** a Supabase, n8n ni Dentalink (verificado con `page.route` que falla ante cualquiera); el test de scroll horizontal corre (y documenta que hoy falla en mobile, como línea base).

### Etapa 1 — Tokens, tema y tipografía (DIS-03, DIS-04, DIS-05) · 3 días
- **Archivos:** `app/globals.css` (reescritura: tokens de §2 en `:root` y `[data-theme=dark]`, `@theme inline`, `@custom-variant dark`, escala tipográfica como utilidades `text-caption…text-display`, radios, sombras, z-index, duraciones, reduced-motion; se borran `card-glow`, `btn-glow`, `text-gradient`, `glass-panel`, `stat-value` y las variables HSL viejas; la skin del chat pasa a los tokens de §2.2.2), `app/layout.tsx` (Inter, script de tema en `<head>`, `viewport` con `themeColor` claro/oscuro y `viewportFit: "cover"`, sin `className="dark"`), `components/theme/tema.ts` (leer/guardar con try/catch), migración de colores crudos en `components/**` (grep de §2.2.5), reemplazo de `text-[Npx]`.
- **Listo cuando:** grep de colores crudos = 0, grep de `text-\[\d+px\]` = 0, grep de `uppercase` = 0, grep de `btn-glow|card-glow|text-gradient` = 0; `scripts/contraste.mjs` pasa en los dos temas; sin flash de tema incorrecto al recargar (captura del primer frame con Playwright en oscuro y claro); capturas de lista y chat actuales en los dos temas.

### Etapa 2 — Primitivas accesibles y `/design` (DIS-06, DIS-07) · 3,5 días
- **Archivos:** `components/ui/{button,icon-button,input,textarea,select,filter-chip,segmented,status-chip,contact-type-badge,avatar,dialog,confirm-dialog,sheet,dropdown-menu,action-sheet,switch,checkbox,tooltip,kbd,skeleton,command-palette}.tsx`, `components/ui/toast.tsx` (cambios de §3.12), `components/ui/estado.tsx` (cambios de §3.18), `app/(app)/design/page.tsx` (solo admin, con todos los estados de §3 y selector de tema y densidad). Dependencias con versión fija: `@radix-ui/react-*` (dialog, dropdown-menu, popover, tooltip, select, switch, toggle-group), `vaul`, `cmdk`. Migración de los 5 modales, 5 switches y toasts propios de `conversation-list.tsx`.
- **Listo cuando:** `/design` muestra cada componente en cada estado de §3; axe sin serious/critical en `/design`; test de Dialog y Sheet: atrapan el foco, cierran con `Esc` y devuelven el foco; grep de `fixed inset-0` y de `role="switch"` fuera de `components/ui` = 0.

### Etapa 3 — Estructura responsive y PWA (MOB-01, MOB-02) · 4 días
- **Archivos:** `app/(app)/layout.tsx` (shell con barra lateral, rail o barra inferior según el ancho, sin el banner con emoji), `components/shell/{sidebar,rail,tab-bar,mobile-header,asiri-pill,mas-sheet}.tsx` (reemplaza `components/sidebar.tsx`), `components/page-header.tsx` (título grande que se achica), `app/manifest.ts` (`start_url: "/conversaciones"` hasta la etapa 6 y `"/atencion"` desde ahí; `display: "standalone"`), íconos 192/512/maskable y `apple-touch-icon` en `public/`, `app/offline/page.tsx`, `app/page.tsx` (inicio por rol), `loading.tsx` por ruta con la forma real (§3.17). Las redirecciones de `next.config.ts` se agregan recién cuando existe la pantalla nueva: `/dashboard → /hoy` en la etapa 8, `/citas → /agenda` en la etapa 9 y `/control → /estado` en la etapa 12.
- **Destinos que todavía no existen** (el backlog construye las etapas en otro orden): la barra inferior, el rail y la barra lateral muestran un destino solo cuando existe su pantalla, y mientras tanto apuntan a la ruta actual.
  - Hasta la etapa 6, el primer lugar de la barra inferior es Hoy (`/dashboard`) y la secretaria entra a `/conversaciones`. Atención toma ese lugar en la etapa 6.
  - Contactos aparece con "Por clasificar" (etapa 7, CRM-04) y abre esa pantalla hasta que exista la lista (CRM-07).
  - Agenda abre `/citas` hasta la etapa 9, y Estado abre `/control` hasta la etapa 12.
- **Listo cuando:** sin scroll horizontal en 360/390/768/1440 en **todas** las rutas actuales; pestañas de la barra inferior ≥ 44 × 44 con badges; ningún emoji en la interfaz; ningún destino lleva a una ruta inexistente; Lighthouse "installable" en verde; abre en standalone sin contenido tapado por la muesca (captura con `safe-area` simulada). La tanda con celulares reales del día siguiente al deploy (backlog §7) la instala en un Android y un iPhone; si algo queda tapado, se vuelve atrás (SEG-08).

### Etapa 4 — Lista de conversaciones v2 y gestos (ATE-04, MOB-03) · 3,5 días
- **Archivos:** `components/conversaciones/conversation-list.tsx` (partido en `lista/{conversation-list,conversation-row,filtros,busqueda,menu-fila}.tsx`), `lib/gestos/use-swipe-action.ts`, `lib/gestos/use-long-press.ts`, `lib/teclado/use-atajos.ts`, `app/(app)/conversaciones/layout.tsx` (en mobile: lista sola en `/conversaciones` y chat a pantalla completa en `[id]`; en escritorio: lista 360 + chat + rail), virtualización con `@tanstack/react-virtual`.
- **Listo cuando:** cada estado de la fila se reconoce en una captura en escala de grises; la hora y el badge pasan AA; con 1.000 ítems demo el scroll va a > 55 fps (traza de Playwright); deslizar con "Deshacer" funciona en un Android y un iPhone reales; todo gesto tiene su botón; `J/K/Enter/Esc/U/H/B/T` funcionan en escritorio.

### Etapa 5 — Chat v2 y chat-view en módulos (ATE-05) · 5 días
- **Archivos:** `components/conversaciones/chat-view.tsx` (2.680 líneas) partido en `chat/{chat-view,chat-header,timeline,bubble,system-message,day-separator,media,adjuntos,composer,search-bar,context-rail,context-sheet,caso-banner}.tsx` y `chat/parsers/{media,turnos,clasif,texto-staff}.ts` con tests unitarios; `lib/use-visual-viewport.ts`; `components/conversaciones/tipo-contacto.tsx` pasa a hoja/rail con motivo (CRM-03); `turno-inline-card.tsx` pasa a `AppointmentCard compact`.
- **Listo cuando:** la timeline ocupa ≥ 65% del alto a 390 px con el teclado cerrado; el composer queda visible con el teclado abierto (iPhone real); ningún archivo pasa de 600 líneas; la meta de las burbujas pasa AA; los parsers tienen tests; **una prueba real de envío** con el número de Lucas, con limpieza en el mismo turno.

### Etapa 6 — Bandeja de Atención (ATE-03; la base es ATE-02) · 4 días
- **Archivos:** `app/(app)/atencion/page.tsx`, `app/(app)/atencion/loading.tsx`, `components/atencion/{bandeja,grupo,caso-card,caso-fila,caso-detalle,resolver-sheet}.tsx`, `lib/fuentes/casos.ts` (demo ahora; real cuando exista la tabla `casos` de ATE-02, que no es parte de esta especificación), `app/(app)/atencion/actions.ts` (Tomar, Esperando, Resolver con devolver a Asiri), badges en `tab-bar` y `sidebar`. El `start_url` del manifest y el inicio de la secretaria pasan a `/atencion`.
- **Antes de la etapa 5:** esta etapa sale antes que el chat en módulos, así que el detalle de escritorio muestra los últimos mensajes en solo lectura y "Abrir chat". El chat embebido con composer (§4.3) entra con la etapa 5 (ATE-05, enero).
- **Listo cuando:** con datos demo, una urgencia, un pago y un "pidió persona" se toman y se resuelven con el pulgar en **2 toques o menos** a 390 px (test de Playwright que cuenta toques); la urgencia se distingue en escala de grises; axe sin serious; `T/W/E` y el salto de foco funcionan en escritorio. Con el backend real: aviso real del número de Lucas visible en < 2 s, con limpieza.

### Etapa 7 — Contactos, ficha y "Por clasificar" (CRM-03, CRM-04, CRM-07, CRM-08 en interfaz) · 6 días
- **Archivos:** `app/(app)/contactos/{page,loading}.tsx` (lista con búsqueda y vistas: Pacientes, Familias, Prospectos, Silenciados, Por clasificar, Dormidos), `app/(app)/contactos/[id]/page.tsx`, `app/(app)/contactos/por-clasificar/page.tsx` (de a uno, botones de 48 px, deshacer, progreso), `app/(app)/contactos/silenciados/page.tsx`, `components/contactos/{ficha,ficha-cabecera,familia,actividad,notas,tipo-sheet,clasificar-card}.tsx`, `lib/fuentes/contactos.ts` (real ya: `pacientes`, `contacto_roles`, turnos de Dentalink y el chat; demo para familias y notas hasta CRM-06).
- **Listo cuando:** desde la ficha se ve todo sin abrir Dentalink; la búsqueda responde en < 300 ms (demo y real); el render no tiene DNI, dirección ni email (test que busca esos campos en el HTML); con datos demo se clasifican 10 contactos en < 60 s a 390 px; silenciar exige motivo; "Equipo" no aparece para quien no es admin.

### Etapa 8 — Hoy (ATE-07) · 2,5 días
- **Archivos:** `app/(app)/hoy/{page,loading}.tsx` (reemplaza `dashboard/page.tsx`), `components/hoy/{estado-asiri,contadores,turnos-hoy,kpi-semana,grafico-mensajes}.tsx` (gráfico con la skill dataviz), `lib/fuentes/hoy.ts`.
- **Listo cuando:** a 390 px el bloque Hoy (estado, 3 contadores y los primeros turnos) entra sin scroll; mirando solo la captura demo se responden: ¿Asiri está prendida?, ¿cuántas urgencias hay abiertas?, ¿cuántos turnos hay mañana?; el gráfico tiene eje y tabla accesible.

### Etapa 9 — Agenda v2 (AGE-04; la fuente por rango es AGE-01) · 5 días
- **Archivos:** `app/(app)/agenda/{page,loading}.tsx` (reemplaza `citas/page.tsx`), `components/agenda/{tira-dias,dia,semana,mes,bloque-turno,hueco,detalle-turno,leyenda,franja-practica}.tsx` (reemplaza `components/citas/calendar.tsx`), `lib/fuentes/agenda.ts` (Dentalink por rango ahora; espejo y agenda propia en sombra después, con la misma interfaz).
- **Listo cuando:** con una semana demo a 390 y 1440, la leyenda se entiende en grises; "Anular" siempre confirma; el modo práctica muestra la franja "esto no toca Dentalink"; **no queda ninguna cita de prueba real**; la vista día carga 1 día y la semana 6, sin el tope de 400.

### Etapa 10 — Recorrido y embudo (REC-02, REC-03 en interfaz) · 4 días
- **Archivos:** `app/(app)/recorrido/{page,loading}.tsx`, `components/recorrido/{franja-embudo,tablero,columna,tarjeta,lista-mobile,stepper,marcar-etapa-sheet,motivos-perdida}.tsx`, `lib/fuentes/recorrido.ts` (demo hasta REC-01).
- **Listo cuando:** 5 recorridos demo distintos se entienden a 390 px; "Perdido" sin motivo está bloqueado; 200 hechos cargan en < 1 s; los conteos demo coinciden con el cálculo de `tests/embudo_baseline.py` sobre las mismas fixtures (cuando haya datos reales, sobre las fuentes reales).

### Etapa 11 — Seguimientos (REC-05 en interfaz) · 3 días
- **Archivos:** `app/(app)/seguimientos/{page,loading}.tsx`, `components/seguimientos/{colas,tarjeta-seguimiento,vista-previa,confirmar-envio,descartar-sheet,tope}.tsx`, `lib/fuentes/seguimientos.ts` (demo; el envío real queda deshabilitado hasta REC-04 y SEG-17).
- **Listo cuando:** ninguna acción manda más de uno a la vez (test); no existe "seleccionar todos" (grep y test); todo texto coincide con una plantilla aprobada e incluye la línea de baja; un contacto con baja no aparece; el tope se ve y bloquea.

### Etapa 12 — Recordatorios, Conocimiento, Estado, Configuración y el resto · 3,5 días
- **Archivos:** `components/recordatorios/recordatorios-panel.tsx` (solo interfaz; **el workflow no se toca**), `components/conocimiento/kb-editor.tsx`, `app/(app)/estado/page.tsx` + `components/estado/*` (reemplaza `control/` y `control-panel.tsx`), `app/(app)/configuracion/**`, y migración a primitivas de `agente/`, `servicios/` y `aprendizaje/`.
- **Listo cuando:** cada pantalla cumple el criterio común; Estado con 4 escenarios demo muestra a 390 px el problema y la acción sin scroll; Apariencia cambia el tema sin recargar y sin flash; El agente muestra el aviso de BOT-14.

### Etapa 13 — Cierre: accesibilidad AA, rendimiento y regresión visual (DIS-08, DIS-09, DIS-10) · 4 días
- **Archivos:** `tests/e2e/a11y.spec.ts` ampliado a todas las rutas y los dos temas, `scripts/objetivos-tactiles.mjs`, instrumentación de Web Vitals sin datos personales (`app/(app)/web-vitals.tsx`), UI optimista con rollback donde falte, `prefetch` de las rutas de la barra inferior, `tests/e2e/regresion-visual.spec.ts` con línea base aprobada y CI en GitHub Actions.
- **Listo cuando:** 0 serious/critical en todas las rutas; Lighthouse accesibilidad ≥ 95 en todas; 0 objetivos chicos; grabación de VoiceOver del flujo Atención → Tomar → Chat → Resolver; zoom al 200% sin pérdida de contenido; LCP < 2,5 s, CLS < 0,05 e INP < 200 ms en `/atencion` y en un chat demo (4G simulado, gama media); un cambio visual no aprobado hace fallar el PR.

### Resumen del esfuerzo

| # | Etapa | Días |
|---|---|---|
| 0 | Modo demo y arnés de capturas | 3 |
| 1 | Tokens, tema y tipografía | 3 |
| 2 | Primitivas accesibles y `/design` | 3,5 |
| 3 | Estructura responsive y PWA | 4 |
| 4 | Lista de conversaciones v2 y gestos | 3,5 |
| 5 | Chat v2 en módulos | 5 |
| 6 | Bandeja de Atención | 4 |
| 7 | Contactos, ficha y Por clasificar | 6 |
| 8 | Hoy | 2,5 |
| 9 | Agenda v2 | 5 |
| 10 | Recorrido y embudo | 4 |
| 11 | Seguimientos | 3 |
| 12 | Recordatorios, Conocimiento, Estado, Configuración y resto | 3,5 |
| 13 | Accesibilidad AA, rendimiento y regresión visual | 4 |
| | **Total** | **54** |

### Cómo encaja con el backlog maestro (replan del 19/10)

Las 14 etapas entran antes del 26/02, en el orden y las fechas de `docs/backlog-maestro-2026-10-19.md` §2, que es el que manda. La decisión de orden ya está tomada y anotada en el backlog (C1, C7 y C8, a cargo de Claude): no queda ninguna para Lucas. Para planificar se usan los días del backlog por ítem, que incluyen el backend de cada épica, y no los de la tabla de arriba.

| Etapa | Ítems del backlog | Arranca | Deploy |
|---|---|---|---|
| 0 | DIS-01 (DIS-02 ya está resuelto acá) | vie 30/10 | Ninguno: solo local |
| 1 | DIS-03, DIS-04, DIS-05 | jue 12/11 | mar 17/11 |
| 2 | DIS-06, DIS-07 | mar 17/11 | vie 20/11 |
| 3 | MOB-01, MOB-02 | jue 19/11 | mar 24/11 (celulares reales: 25/11) |
| 6 | ATE-03 (su base, ATE-02, es del 26/11) | lun 30/11 | mié 02/12 |
| 7 (parte 1) | CRM-03, CRM-04 | mié 02/12 | vie 04/12 |
| 4 | ATE-04, MOB-03 | jue 17/12, en una rama | lun 04/01 (celulares reales: 05/01) |
| 5 | ATE-05 | mié 06/01 | lun 11/01 (celulares reales: 12/01) |
| 7 (parte 2) | CRM-07, CRM-08, CRM-05 | lun 11/01 | enero |
| 10 | REC-02, REC-03 | lun 18/01 | enero |
| 11 | REC-05 | mar 26/01 | enero |
| 8 | ATE-07 | jue 28/01 | vie 29/01 |
| 9 | AGE-04 | jue 04/02, en una rama | mié 10/02 |
| 12 | SEG-15 | lun 15/02 | antes del vie 19/02 |
| 13 | DIS-08, DIS-09, DIS-10 | mié 17/02 | vie 19/02 (último deploy del panel) |

El backend de esas épicas (casos, familias, eventos, canal de seguimientos, espejo) tiene sus propios ítems y dependencias, incluido el contrato (SEG-17). La interfaz no lo espera: arranca sobre el adaptador demo y se enchufa cuando llega.
