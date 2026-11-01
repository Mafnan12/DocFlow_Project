from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FilesConfig(BaseModel):
    allowed_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "application/pdf"]
    )
    max_file_mb: int = 10
    max_pdf_pages: int = 3
    max_image_pixels: int = 40_000_000


class PreprocessConfig(BaseModel):
    max_long_side_px: int = 2000
    auto_rotate_exif: bool = True
    deskew: bool = True
    contrast_enhance: bool = False


class PDFConfig(BaseModel):
    use_text_layer_if_present: bool = True
    min_text_layer_chars: int = 50
    render_dpi: int = 200


class OCRConfig(BaseModel):
    engine: Literal["paddle", "tesseract", "doctr"] = "paddle"
    min_word_confidence: float = 0.0


class ApproachesConfig(BaseModel):
    text: bool = True
    vision: bool = True
    run_in_parallel: bool = True


class AgentConfig(BaseModel):
    enabled: bool = True
    max_correction_rounds: int = 2
    zoom_factor: float = 2.0


class ClassificationConfig(BaseModel):
    reject_other: bool = True


class PipelineConfig(BaseModel):
    files: FilesConfig = Field(default_factory=FilesConfig)
    preprocess: PreprocessConfig = Field(default_factory=PreprocessConfig)
    pdf: PDFConfig = Field(default_factory=PDFConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    approaches: ApproachesConfig = Field(default_factory=ApproachesConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    classification: ClassificationConfig = Field(default_factory=ClassificationConfig)


class ToleranceConfig(BaseModel):
    absolute: str = "0.05"
    relative: float = 0.005
    zero_decimal_currencies: list[str] = Field(default_factory=lambda: ["IDR", "JPY", "KRW"])


class DateBoundsConfig(BaseModel):
    min_year: int = 2000
    max_year: int = 2026


class ValidationConfig(BaseModel):
    tolerance: ToleranceConfig = Field(default_factory=ToleranceConfig)
    date: DateBoundsConfig = Field(default_factory=DateBoundsConfig)
    required_fields: dict[str, list[str]] = Field(default_factory=dict)
    critical_fields: list[str] = Field(
        default_factory=lambda: ["vendor_name", "date", "currency", "total"]
    )
    known_currencies: list[str] = Field(
        default_factory=lambda: ["MYR", "IDR", "USD", "EUR", "GBP", "PKR", "SGD", "AED"]
    )


class ConfidenceSignalsConfig(BaseModel):
    agreement_weight: float = 0.45
    validation_weight: float = 0.35
    ocr_support_weight: float = 0.10
    no_correction_weight: float = 0.10


class AutoApproveRequiresConfig(BaseModel):
    all_critical_fields_above_threshold: bool = True
    all_validation_rules_pass: bool = True
    doc_type_confidence_min: float = 0.8


class ConfidenceConfig(BaseModel):
    signals: ConfidenceSignalsConfig = Field(default_factory=ConfidenceSignalsConfig)
    field_threshold: float = 0.70
    auto_approve_requires: AutoApproveRequiresConfig = Field(
        default_factory=AutoApproveRequiresConfig
    )
    tuned_on: str = "dev split"


class ModelRoleConfig(BaseModel):
    models: list[dict[str, Any]] = Field(default_factory=list)
    temperature: float = 0.0
    timeout_seconds: int = 30
    max_retries: int = 2


class LLMCacheConfig(BaseModel):
    enabled: bool = True
    ttl_seconds: int = 86400
    storage_dir: str = ".cache/llm"


class LLMConfig(BaseModel):
    roles: dict[str, ModelRoleConfig] = Field(default_factory=dict)
    cache: LLMCacheConfig = Field(default_factory=LLMCacheConfig)


class DemoUser(BaseModel):
    user_id: str
    display_name: str
    role: Literal["bookkeeper", "admin"]


class DemoClient(BaseModel):
    client_id: str
    name: str


class DemoConfig(BaseModel):
    users: list[DemoUser] = Field(default_factory=list)
    clients: list[DemoClient] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Base paths
    BASE_DIR: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)
    CONFIG_DIR: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent / "config"
    )

    # API Keys
    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    GITHUB_TOKEN: str | None = None
    OPENROUTER_API_KEY: str | None = None

    # Database and Storage
    DATABASE_URL: str = (
        "postgresql+psycopg://doc:doc@localhost:5432/docflow"  # pragma: allowlist secret
    )
    STORAGE_BACKEND: Literal["local", "supabase"] = "local"
    LOCAL_STORAGE_DIR: str = "./storage"
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_KEY: str | None = None
    SUPABASE_BUCKET: str = "documents"

    # Auth
    JWT_SECRET: str = "insecure-dev-secret-change-in-production"
    JWT_EXPIRES_MINUTES: int = 720

    # Observability
    LANGFUSE_PUBLIC_KEY: str | None = None
    LANGFUSE_SECRET_KEY: str | None = None
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # App
    APP_ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    WORKER_CONCURRENCY: int = 1
    BACKEND_URL: str = "http://localhost:8000"

    # Loaded YAML configs
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    confidence: ConfidenceConfig = Field(default_factory=ConfidenceConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    demo: DemoConfig = Field(default_factory=DemoConfig)

    def load_yaml_configs(self) -> None:
        """Load YAML configuration files from CONFIG_DIR."""
        if not self.CONFIG_DIR.exists():
            return

        pipeline_file = self.CONFIG_DIR / "pipeline.yaml"
        if pipeline_file.exists():
            with open(pipeline_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.pipeline = PipelineConfig.model_validate(data)

        validation_file = self.CONFIG_DIR / "validation.yaml"
        if validation_file.exists():
            with open(validation_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.validation = ValidationConfig.model_validate(data)

        confidence_file = self.CONFIG_DIR / "confidence.yaml"
        if confidence_file.exists():
            with open(confidence_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.confidence = ConfidenceConfig.model_validate(data)

        llm_file = self.CONFIG_DIR / "llm.yaml"
        if llm_file.exists():
            with open(llm_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.llm = LLMConfig.model_validate(data)

        demo_file = self.CONFIG_DIR / "demo.yaml"
        if demo_file.exists():
            with open(demo_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                self.demo = DemoConfig.model_validate(data)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.load_yaml_configs()
    return settings
