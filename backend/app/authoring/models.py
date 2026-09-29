from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class CreationRequest(Strict):
    topic: str = Field(default='', max_length=12000)
    audience: str = Field(min_length=1, max_length=500)
    length_preference: Literal['auto', 'brief', 'standard', 'detailed'] = 'auto'
    source: Literal['topic', 'pdf'] = 'topic'


class VisualPlan(Strict):
    kind: Literal['text_only', 'diagram', 'chart', 'plot', 'equation', 'table', 'source_figure']
    description: str = Field(min_length=1, max_length=800)
    reason: str = Field(min_length=1, max_length=500)


class OutlineSlide(Strict):
    kind: Literal['opening', 'content', 'closing'] = 'content'
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,40}$')
    title: str = Field(min_length=1, max_length=180)
    points: list[str] = Field(min_length=1, max_length=10)
    source_pages: list[int] = Field(default_factory=list, max_length=100)
    visual: VisualPlan | None = None  # Older saved outlines remain readable.


class Outline(Strict):
    title: str = Field(min_length=1, max_length=180)
    rationale: str = Field(min_length=1, max_length=2000)
    slides: list[OutlineSlide] = Field(min_length=1, max_length=30)
    @model_validator(mode='after')
    def unique_ids(self):
        if len({s.id for s in self.slides}) != len(self.slides):
            raise ValueError('Outline slide IDs must be unique.')
        return self


class Series(Strict):
    name: str = Field(min_length=1, max_length=100)
    values: list[float] = Field(min_length=1, max_length=500)


class ChartSpec(Strict):
    kind: Literal['bar', 'column', 'line', 'pie', 'area', 'scatter']
    categories: list[str] = Field(min_length=1, max_length=100)
    series: list[Series] = Field(min_length=1, max_length=6)
    x_label: str = Field(default='', max_length=100)
    y_label: str = Field(default='', max_length=100)
    @model_validator(mode='after')
    def lengths(self):
        if any(len(s.values) != len(self.categories) for s in self.series):
            raise ValueError('Chart data must match categories.')
        if self.kind == 'pie' and (len(self.series) != 1 or any(v < 0 for v in self.series[0].values)):
            raise ValueError('Pie charts need one nonnegative series.')
        if self.kind == 'scatter':
            for x in self.categories:
                float(x)
        return self


class Annotation(Strict):
    x: float
    y: float
    label: str = Field(min_length=1, max_length=100)


class PlotSpec(Strict):
    kind: Literal['function', 'scatter', 'histogram', 'heatmap'] = 'function'
    functions: list[str] = Field(default_factory=list, max_length=5)
    x_min: float = -5
    x_max: float = 5
    x: list[float] = Field(default_factory=list, max_length=2000)
    y: list[float] = Field(default_factory=list, max_length=2000)
    matrix: list[list[float]] = Field(default_factory=list, max_length=50)
    x_label: str = Field(default='x', max_length=100)
    y_label: str = Field(default='y', max_length=100)
    log_x: bool = False
    log_y: bool = False
    tick_values: list[float] = Field(default_factory=list, max_length=20)
    tick_labels: list[str] = Field(default_factory=list, max_length=20)
    annotations: list[Annotation] = Field(default_factory=list, max_length=20)
    @model_validator(mode='after')
    def bounded(self):
        if not -1e6 <= self.x_min < self.x_max <= 1e6:
            raise ValueError('Invalid plot domain.')
        if any(len(row) > 50 for row in self.matrix):
            raise ValueError('Heatmap exceeds 50 columns.')
        if len(self.tick_values) != len(self.tick_labels):
            raise ValueError('Tick labels must match tick values.')
        return self


class Citation(Strict):
    page: int = Field(ge=1, le=100)
    quote: str = Field(min_length=1, max_length=2000)


class TableSpec(Strict):
    headers: list[str] = Field(min_length=1, max_length=6)
    rows: list[list[str]] = Field(min_length=1, max_length=10)
    @model_validator(mode='after')
    def rectangular(self):
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError('Table rows must match the header count.')
        if any(len(cell)>100 for row in [self.headers]+self.rows for cell in row):
            raise ValueError('Table cells must be concise for slide readability.')
        return self


class DiagramNode(Strict):
    label: str = Field(min_length=1, max_length=45)
    detail: str = Field(default='', max_length=100)


class DiagramSpec(Strict):
    kind: Literal['process', 'comparison']
    nodes: list[DiagramNode] = Field(min_length=2, max_length=6)

    @model_validator(mode='after')
    def readable(self):
        if len(self.nodes)>4 and any(len(n.detail)>55 for n in self.nodes):
            raise ValueError('Five or six diagram steps need details of at most 55 characters each.')
        return self


class SlideSpec(Strict):
    id: str
    title: str = Field(min_length=1, max_length=180)
    bullets: list[str] = Field(default_factory=list, max_length=8)
    notes: str = Field(default='', max_length=8000)
    chart: ChartSpec | None = None
    plot: PlotSpec | None = None
    equation: str | None = Field(default=None, max_length=1000)
    figure_page: int | None = Field(default=None, ge=1, le=100)
    table: TableSpec | None = None
    diagram: DiagramSpec | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    @model_validator(mode='after')
    def readable(self):
        if sum(len(b) for b in self.bullets) > 1400 or any(len(b) > 500 for b in self.bullets):
            raise ValueError('Slide is too dense; shorten it or revise the outline.')
        if sum(x is not None for x in (self.chart, self.plot, self.equation, self.figure_page, self.table, self.diagram)) > 1:
            raise ValueError('Use one major visual per slide.')
        return self


class DeckSpec(Strict):
    slides: list[SlideSpec] = Field(min_length=1, max_length=30)
