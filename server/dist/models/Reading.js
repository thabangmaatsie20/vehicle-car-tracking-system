"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ReadingModel = void 0;
const mongoose_1 = __importStar(require("mongoose"));
const GpsSchema = new mongoose_1.Schema({
    latitude: { type: Number, required: true },
    longitude: { type: Number, required: true },
    speedKph: Number,
    satellites: Number,
    hdop: Number,
}, { _id: false });
const SensorSchema = new mongoose_1.Schema({}, { strict: false, _id: false });
const ReadingSchema = new mongoose_1.Schema({
    deviceId: { type: String, required: true, index: true },
    type: { type: String, enum: ['telemetry', 'gps', 'sensor'], default: 'telemetry' },
    gps: { type: GpsSchema, required: false },
    sensors: { type: SensorSchema, required: false },
    createdAt: { type: Date, default: Date.now, index: true },
});
ReadingSchema.index({ deviceId: 1, createdAt: -1 });
exports.ReadingModel = mongoose_1.default.model('Reading', ReadingSchema);
