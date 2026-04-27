export const environment = {
    production: false,
    apiUrl: '/ask',
    ui: {
        title: "Tech Radar Explorer",
        subtitle: "Analiza la evolución tecnológica y tendencias basadas en los volúmenes del Thoughtworks Technology Radar.",
        icon: "🔍",
        examples: [
        "¿Cómo han evolucionado las herramientas asociadas a la IA en los dos últimos años?",
        "¿Qué tecnologías han pasado a la fase de 'Adopt' recientemente?",
        "¿Qué riesgos se mencionan respecto al uso de LLMs en producción?",
        "Analiza la evolución de las plataformas de datos desde 2023."
],
        disclaimer: "Tech Radar Explorer utiliza IA para sintetizar información. Verifica siempre los volúmenes originales del Radar de Thoughtworks.",
        defaultModelId: "eu.amazon.nova-lite-v1:0",
        defaultMaxTokens: 2048,
        defaultNumResults: 20,
        models: [
            { label: "Nova Micro",        id: "eu.amazon.nova-micro-v1:0" },
            { label: "Nova Lite",         id: "eu.amazon.nova-lite-v1:0" },
            { label: "Nova 2 Lite",       id: "eu.amazon.nova-2-lite-v1:0" },
            { label: "Nova Pro",          id: "eu.amazon.nova-pro-v1:0" },
            { label: "Claude Sonnet 4.6", id: "eu.anthropic.claude-sonnet-4-6" }
        ],
        filterOptions: {
            rings: ['Adopt', 'Trial', 'Assess', 'Hold'],
            quadrants: ['Techniques', 'Tools', 'Platforms', 'Languages and Frameworks'],
            editions: ['Oct 2024', 'Apr 2025', 'Nov 2025', 'Apr 2026'],
        },
    },
};
