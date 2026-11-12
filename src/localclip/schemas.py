from typing import Literal
import math
from pydantic import BaseModel, ConfigDict, Field, model_validator

GENRES = ['Auto', 'Podcast', 'Lifestyle', 'Vlog', 'Viagem', 'Comida', 'Beleza', 'Fitness', 'Esportes', 'Futebol', 'Basquete', 'Marketing', 'Talking Head', 'Discurso', 'Comentário', 'Entrevista', 'Entretenimento', 'Filmes', 'Reality', 'Notícias', 'Educacional', 'Produtos', 'História', 'Ciência e tecnologia', 'Música', 'Games', 'Outros']
DURATIONS = ['Auto', '<30s', '30s–59s', '60s–89s', '90s–3min', '3min–5min', '5min–10min', 'personalizada']
CLIP_MODELS = ['Auto', 'Conversa / Talking Head', 'Multimodal / Clip Anything']
PLATFORMS = ['TikTok', 'YouTube Shorts', 'Instagram Reels']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Options(StrictModel):
    clip_model: str = 'Auto'
    genre: str = 'Auto'
    duration: str = 'Auto'  # Legacy single-selection requests.
    durations: list[str] | None = None
    custom_min: float = Field(15, ge=1, le=3600)
    custom_max: float = Field(60, ge=1, le=3600)
    format: Literal['9:16', '1:1', '16:9'] = '9:16'
    platform: str = 'TikTok'
    auto_title: bool = True
    reframe: bool = True
    subtitles: bool = True
    subtitle_style: Literal['classic', 'highlight'] = 'highlight'
    subtitle_size: int = Field(48, ge=12, le=120)
    subtitle_position: Literal['bottom', 'center', 'top'] = 'bottom'
    request: str = Field('', max_length=4000)
    start: float = Field(0, ge=0)
    end: float | None = Field(None, gt=0)
    results: int | None = None  # Legacy requests; selection is automatic.
    allow_images: bool = False

    @model_validator(mode='after')
    def validate_options(self):
        for key, choices in [('genre', GENRES), ('clip_model', CLIP_MODELS), ('platform', PLATFORMS)]:
            if getattr(self, key) not in choices:
                raise ValueError(f'Opção inválida: {key}')
        durations = self.durations if self.durations is not None else [self.duration]
        if not durations or len(durations) != len(set(durations)) or any(d not in DURATIONS for d in durations):
            raise ValueError('Selecione ao menos uma duração válida, sem repetição.')
        if 'Auto' in durations and len(durations) != 1:
            raise ValueError('Auto não pode ser combinado com durações manuais.')
        self.durations = durations
        self.duration = durations[0] if len(durations) == 1 else 'Auto'
        self.results = None
        self.reframe = True
        self.subtitles = True
        if self.end is not None and self.end <= self.start:
            raise ValueError('Fim deve ser posterior ao início.')
        if self.custom_max < self.custom_min:
            raise ValueError('Duração máxima deve ser maior ou igual à mínima.')
        return self

class Word(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    word: str = Field(max_length=500)

    @model_validator(mode='after')
    def interval(self):
        if self.end <= self.start:
            raise ValueError('Palavra com intervalo inválido.')
        return self

class Interval(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode='after')
    def interval(self):
        if self.end <= self.start:
            raise ValueError('Intervalo vazio ou invertido.')
        return self

class Edit(StrictModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = Field(max_length=250)
    format: Literal['9:16', '1:1', '16:9'] = '9:16'
    reframe: bool = True
    auto_zoom: bool = True
    zoom_level: float = Field(1.25, ge=1.0, le=2.5)
    subtitles: bool = True
    subtitle_style: Literal['classic', 'highlight'] = 'highlight'
    subtitle_size: int = Field(48, ge=12, le=120)
    subtitle_position: Literal['bottom', 'center', 'top'] = 'bottom'
    crop_x: float | None = Field(None, ge=0, le=1)
    remove_ranges: list[Interval] = Field(default_factory=list, max_length=100)
    words: list[Word] = Field(default_factory=list, max_length=50000)

    @model_validator(mode='after')
    def check_ranges(self):
        if self.end <= self.start:
            raise ValueError('Fim deve ser posterior ao início.')
        last = self.start
        total = 0.
        for r in sorted(self.remove_ranges, key=lambda r: r.start):
            if r.start < last or r.end > self.end:
                raise ValueError('Remoções devem ser internas e não sobrepostas.')
            last = r.end
            total += r.end-r.start
        if total >= self.end-self.start:
            raise ValueError('Não é possível remover todo o clipe.')
        for word in self.words:
            if word.start < self.start or word.end > self.end:
                raise ValueError('Palavras devem estar dentro do clipe.')
        return self

class Provider(StrictModel):
    kind: Literal['openai', 'gemini', 'anthropic', 'compatible', 'glm', 'omp', 'openrouter']
    model: str = Field(min_length=1, max_length=150)
    base_url: str = Field('', max_length=2048)
    enabled: bool = True
    api_key: str | None = Field(None, max_length=20000)

class OmpLogin(StrictModel):
    provider: str = Field(min_length=1, max_length=64)
    google_cloud_project: str | None = Field(None, max_length=128, pattern=r'^[a-z][a-z0-9-]{4,62}[a-z0-9]$')
class ProviderOrder(StrictModel):
    primary: str | None = None
    fallback: str | None = None

class URLInput(StrictModel):
    url: str = Field(min_length=8, max_length=4096)

class ProjectRename(StrictModel):
    display_name: str = Field(min_length=1, max_length=250)

    @model_validator(mode='after')
    def clean_name(self):
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError('Informe um nome para o vídeo.')
        return self
