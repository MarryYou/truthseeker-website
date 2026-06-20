import { create } from 'zustand';
import { message } from '@/lib/antd';
import * as settingsService from '@/services/settings';
import type {
  UserSecret,
  ModelAsset,
  ResearchPreset,
  SettingsSchema,
} from '@/types';

interface SettingsState {
  // --- UI 状态 ---
  activeTab: 'profile' | 'connections' | 'registry' | 'workflow';
  loading: boolean;
  saveLoading: boolean;

  // 后端导出的 Schema
  schema: SettingsSchema | null;

  // 1. 凭证列表
  secrets: UserSecret[];
  dirtySecrets: Record<string, boolean>;

  // 2. 资产列表 (Models)
  assets: ModelAsset[];
  originalAssets: ModelAsset[];

  // 3. 预设列表
  presets: ResearchPreset[];
  activePresetId: string | null;

  // --- Actions ---
  setActiveTab: (tab: SettingsState['activeTab']) => void;
  setActivePresetId: (id: string) => void;
  fetchSchema: () => Promise<void>;
  fetchSettings: () => Promise<void>;

  // 更新本地临时状态
  updateLocalSecret: (providerName: string, data: Partial<UserSecret & { plain_key?: string }>) => void;
  updateLocalAsset: (assetId: string, data: Partial<ModelAsset>) => void;
  updateLocalPreset: (presetId: string, data: Partial<ResearchPreset>) => void;

  // 全局保存
  applyChanges: () => Promise<void>;

  // 预设 CRUD
  createPreset: (name: string, description?: string) => Promise<ResearchPreset | null>;
  deletePreset: (presetId: string) => Promise<boolean>;

  // 测试连接
  testConnection: (providerName: string) => Promise<{ success: boolean; latency?: number; error?: string }>;
  disabledModelIds: string[];
  toggleModelActive: (assetId: string) => void;
}

export const useSettingsStore = create<SettingsState>((set, get) => ({
  activeTab: 'connections',
  loading: false,
  saveLoading: false,
  schema: null,
  secrets: [],
  dirtySecrets: {},
  assets: [],
  originalAssets: [],
  presets: [],
  activePresetId: null,
  disabledModelIds: typeof window !== 'undefined' ? JSON.parse(localStorage.getItem('truth_seeker_disabled_model_ids') || '[]') : [],

  setActiveTab: (tab) => set({ activeTab: tab }),
  setActivePresetId: (id) => set({ activePresetId: id }),

  fetchSchema: async () => {
    if (get().schema) return;
    try {
      const schema = await settingsService.getSettingsSchema();
      set({ schema });
    } catch (err) {
      console.error('Fetch schema failed:', err);
    }
  },

  fetchSettings: async () => {
    set({ loading: true });
    try {
      const [secrets, assets, presets] = await Promise.all([
        settingsService.getSecrets(),
        settingsService.getAssets(),
        settingsService.getPresets(),
        get().fetchSchema(),
      ]);

      set({
        secrets,
        dirtySecrets: {},
        assets,
        originalAssets: assets,
        presets,
        activePresetId: presets.length > 0 ? (presets.find(p => p.is_default)?.id || presets[0].id) : null,
      });
    } catch (err) {
      console.error('Fetch settings failed:', err);
      message.error('加载设置失败');
    } finally {
      set({ loading: false });
    }
  },

  updateLocalSecret: (providerName, data) => {
    set((state) => ({
      secrets: state.secrets.map(s => s.provider_name === providerName ? { ...s, ...data } : s),
      dirtySecrets: { ...state.dirtySecrets, [providerName]: true },
    }));
  },

  updateLocalAsset: (assetId, data) => {
    set((state) => ({
      assets: state.assets.map(a => a.id === assetId ? { ...a, ...data } : a),
    }));
  },

  updateLocalPreset: (presetId, data) => {
    set((state) => ({
      presets: state.presets.map(p => p.id === presetId ? { ...p, ...data } : p),
    }));
  },

  applyChanges: async () => {
    const { secrets, assets, originalAssets, dirtySecrets, presets } = get();
    set({ saveLoading: true });
    try {
      // 1. 先保存 Presets (将可能解绑的关系写入后端，释放对要删除资产的引用)
      for (const p of presets) {
        await settingsService.upsertPreset(p);
      }

      // 2. 删除已被注销的模型资产
      const deletedAssets = originalAssets.filter(oa => !assets.some(a => a.id === oa.id));
      for (const da of deletedAssets) {
        await settingsService.deleteAsset(da.id);
      }

      // 3. 保存/注册 Assets
      for (const a of assets) {
        await settingsService.upsertAsset(a);
      }

      // 4. 保存/注销 Secrets
      const modifiedSecrets = secrets.filter(s => dirtySecrets[s.provider_name]);
      for (const s of modifiedSecrets) {
        let pk = (s as UserSecret & { plain_key?: string }).plain_key;
        if (pk === '••••••••••••••••') {
          pk = undefined;
        } else if (pk === '') {
          pk = '';
        }
        await settingsService.upsertSecret(
          s.category,
          s.provider_name,
          pk,
          s.base_url,
        );
      }

      message.success('设置已成功同步');
      await get().fetchSettings();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      console.error('Apply changes failed:', err);
      message.error(error.response?.data?.detail || '保存失败');
    } finally {
      set({ saveLoading: false });
    }
  },

  createPreset: async (name, description) => {
    try {
      const newPreset = await settingsService.createPreset(name, description);
      set((state) => ({
        presets: [...state.presets, newPreset],
        activePresetId: newPreset.id,
      }));
      message.success(`预设【${name}】创建成功`);
      return newPreset;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error(error.response?.data?.detail || '创建预设失败');
      return null;
    }
  },

  deletePreset: async (presetId) => {
    try {
      await settingsService.deletePreset(presetId);
      set((state) => {
        const remaining = state.presets.filter(p => p.id !== presetId);
        return {
          presets: remaining,
          activePresetId: state.activePresetId === presetId
            ? (remaining[0]?.id || null)
            : state.activePresetId,
        };
      });
      message.success('预设已删除');
      return true;
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      message.error(error.response?.data?.detail || '删除预设失败');
      return false;
    }
  },

  testConnection: async (providerName) => {
    const secret = get().secrets.find(s => s.provider_name === providerName);
    if (!secret) return { success: false, error: '未找到服务商' };

    try {
      const data = await settingsService.testConnection({
        provider_name: providerName,
        plain_key: (secret as UserSecret & { plain_key?: string }).plain_key,
        base_url: secret.base_url,
      });
      return { success: true, latency: data.latency };
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } }; message?: string };
      return { success: false, error: error.response?.data?.detail || '连接超时' };
    }
  },

  toggleModelActive: (assetId) => {
    set((state) => {
      const isAlreadyDisabled = state.disabledModelIds.includes(assetId);
      const nextDisabled = isAlreadyDisabled
        ? state.disabledModelIds.filter(id => id !== assetId)
        : [...state.disabledModelIds, assetId];
      if (typeof window !== 'undefined') {
        localStorage.setItem('truth_seeker_disabled_model_ids', JSON.stringify(nextDisabled));
      }
      return { disabledModelIds: nextDisabled };
    });
  },
}));
