"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getMovementInsights = getMovementInsights;
const Reading_1 = require("./models/Reading");
async function getMovementInsights(opts) {
    const { deviceId, fromTs, toTs, limit = 200, model = process.env.DEEPSEEK_MODEL || 'deepseek-chat', apiKey } = opts;
    const query = { deviceId };
    if (fromTs || toTs) {
        query.createdAt = {};
        if (fromTs)
            query.createdAt.$gte = new Date(fromTs);
        if (toTs)
            query.createdAt.$lte = new Date(toTs);
    }
    const readings = await Reading_1.ReadingModel.find(query, { gps: 1, createdAt: 1 })
        .sort({ createdAt: -1 })
        .limit(limit)
        .lean();
    const points = readings
        .filter(r => r.gps && typeof r.gps.latitude === 'number' && typeof r.gps.longitude === 'number')
        .map(r => ({ ts: r.createdAt.toISOString(), lat: r.gps.latitude, lon: r.gps.longitude, speedKph: r.gps?.speedKph ?? null }));
    const prompt = [
        'You are an IoT mobility analyst. Analyze the following GPS track points for unusual movement patterns, speed anomalies, or suspicious stops.',
        'Return a short, actionable summary with bullet points and a confidence score (0-1).',
        'Focus on: sudden jumps, abnormal speed, erratic paths, or unexpected stationary periods.',
        `Device: ${deviceId}`,
        `Points (most recent first, up to ${limit}):`,
        JSON.stringify(points, null, 2)
    ].join('\n');
    // DeepSeek API - compatible with OpenAI style chat completions
    const response = await fetch('https://api.deepseek.com/v1/chat/completions', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${apiKey}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            model,
            messages: [
                { role: 'system', content: 'You are a helpful assistant for IoT analytics.' },
                { role: 'user', content: prompt }
            ],
            temperature: 0.2,
            max_tokens: 400
        })
    });
    if (!response.ok) {
        const text = await response.text();
        throw new Error(`DeepSeek API error: ${response.status} ${text}`);
    }
    const json = await response.json();
    const content = json.choices?.[0]?.message?.content?.trim();
    return content || 'No insight generated.';
}
