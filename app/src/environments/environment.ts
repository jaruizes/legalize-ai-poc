export const environment = {
  production: false,
  // Proxied through proxy.conf.json during development.
  // Update proxy.conf.json with the API Gateway base URL.
  apiUrl: '/ask',
  ui: {
    "title": "Consulta leyes",
    "subtitle": "Pregunta sobre la legislación española y obtén respuestas con referencias a los documentos oficiales.",
    "icon": "⚖️",
    "examples": [
        "¿Cuáles son los requisitos para constituir una sociedad de responsabilidad limitada?",
        "¿Qué establece la Constitución Española sobre el derecho a la vivienda?",
        "¿Cuántos días de vacaciones tiene un trabajador según el Estatuto de los Trabajadores?",
        "¿Cuáles son las causas de extinción de un contrato de trabajo?"
    ],
    "disclaimer": "Consulta leyes puede cometer errores. Verifica siempre la información con fuentes oficiales (BOE, BOJA, etc.)."
}
};
