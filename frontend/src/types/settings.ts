// --- 凭证层 ---

export interface UserSecret {
  category: 'llm' | 'search';
  provider_name: string;
  is_configured: boolean;
  base_url?: string;
  updated_at?: string;
}

// --- 资产层 ---

export interface ModelAsset {
  id: string;
  provider_name: string;
  model_name: string;
  display_name?: string;
  capabilities?: string[];
  is_system_default?: boolean;
}

// --- 策略层 ---

export interface PresetStageConfig {
  asset_id: string | null;
  temperature?: number;
  max_tokens?: number;
  timeout?: number;
  params?: Record<string, unknown>;
}

/** 预设中的业务参数（可扩展）*/
export interface PresetBusiness {
  speed: 'fast_react' | 'expert_search' | 'research_pipeline';
  engines: string[];
  max_results_per_query: number | { min: number; max: number };
  max_search_rounds?: number | { min: number; max: number };
  intent_max_dimensions?: number | { min: number; max: number };
  keywords_per_dimension?: number | { min: number; max: number };
  allow_ai_override?: boolean;
  bilingual?: boolean;
  include_year?: boolean;
  verification_level?: 'skip' | 'standard' | 'strict';
  [key: string]: unknown;
}

export interface PresetNodesConfig {
  stages: Record<string, PresetStageConfig>;
  business: PresetBusiness;
}

export interface ResearchPreset {
  id: string;
  name: string;
  description?: string;
  nodes_config: PresetNodesConfig;
  is_default: boolean;
  is_active: boolean;
  is_system_default?: boolean;
}

// --- Schema (动态参数描述) ---

export interface ParamSchema {
  type: 'bool' | 'enum' | 'int' | 'float' | 'string' | 'str' | 'dict';
  default?: unknown;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
  description?: string;
  /** 引用 enums 字典中的 key 名 (单选枚举) */
  enum?: string;
  /** 引用 enums 字典中的 key 名 (多选枚举) */
  item_enum?: string;
  /** list 类型的元素类型 (如 "str") */
  item_type?: string;
}

export interface SettingsSchema {
  node_params: Record<string, Record<string, ParamSchema>>;
  preset_params: Record<string, ParamSchema>;
  enums: Record<string, string[] | Record<string, string[]>>;
  speed_profiles: Record<string, { label: string; description: string }>;
}

// --- 连接测试 ---

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  latency_ms?: number;
}
