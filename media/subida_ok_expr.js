(() => {
  const sc = Number($json.statusCode);
  const body = $json.body;
  return !$json.error && sc >= 200 && sc < 300 && !(body && typeof body === 'object' && body.error);
})()
