import api from './api';
import type {
  UserSecret,
  ModelAsset,
  ResearchPreset,
  SettingsSchema,
} from '@/types';

export type { UserSecret, ModelAsset, ResearchPreset, SettingsSchema };

// ── 1. 凭证层 (Secrets/Providers) ───────────────────────────────────

export const getSecrets = async (): Promise<UserSecret[]> => {
  const { data } = await api.get<UserSecret[]>('/settings/secrets');
  return data;
};

export const upsertSecret = async (
  category: string,
  provider_name: string,
  plain_key: string | null | undefined,
  base_url?: string,
) => {
  const { data } = await api.put('/settings/secrets', {
    category,
    provider_name,
    plain_key,
    base_url,
  });
  return data;
};

// ── 2. 资产层 (Assets/Models) ───────────────────────────────────────

export const getAssets = async (): Promise<ModelAsset[]> => {
  const { data } = await api.get<ModelAsset[]>('/settings/assets');
  return data;
};

export const upsertAsset = async (asset: Partial<ModelAsset>) => {
  const { data } = await api.put('/settings/assets', asset);
  return data;
};

export const deleteAsset = async (assetId: string) => {
  const { data } = await api.delete(`/settings/assets/${assetId}`);
  return data;
};

// ── 3. 策略层 (Presets) ─────────────────────────────────────────────

export const getPresets = async (): Promise<ResearchPreset[]> => {
  const { data } = await api.get<ResearchPreset[]>('/settings/presets');
  return data;
};

export const upsertPreset = async (preset: Partial<ResearchPreset>) => {
  const { data } = await api.put('/settings/presets', preset);
  return data;
};

export const createPreset = async (name: string, description?: string) => {
  const { data } = await api.post<ResearchPreset>('/settings/presets', { name, description });
  return data;
};

export const deletePreset = async (presetId: string) => {
  const { data } = await api.delete(`/settings/presets/${presetId}`);
  return data;
};

// ── 4. 交互增强 (Fetch Models) ──────────────────────────────────────

export const fetchRemoteModels = async (
  provider_name: string,
  config?: { plain_key?: string; base_url?: string },
): Promise<string[]> => {
  const { data } = await api.post<string[]>(`/settings/providers/${provider_name}/fetch-models`, config);
  return data;
};

// ── 5. 连接性测试 ───────────────────────────────────────────────────

export const testConnection = async (config: {
  provider_name: string;
  model_name?: string;
  base_url?: string;
  plain_key?: string;
}) => {
  const { data } = await api.post('/settings/test-connection', config);
  return data;
};

// ── 6. 获取后端动态 Schema ──────────────────────────────────────────

export const getSettingsSchema = async (): Promise<SettingsSchema> => {
  const { data } = await api.get<SettingsSchema>('/settings/schema');
  return data;
};
