const fraseFrustracion = /(^|\s)(repito|ya te dije|ya dije|reitero|como te dije|otra vez te digo|no entiendo|no me entend[eé]s|insisto|cuantas veces)([\s,.!?]|$)/i;
const userText = String(trigger.text || '').toLowerCase();
const is_frustrated = fraseFrustracion.test(userText);