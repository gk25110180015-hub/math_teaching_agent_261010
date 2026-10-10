"""Model-owned short frame headings; immutable source payloads stay renderer-owned."""
from pathlib import Path

from pydantic import Field, model_validator

from .domain import StrictModel
from .util import AgentError, digest


class FrameTitle(StrictModel):
    frame_id: str
    title: str = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def plain_heading(self):
        if not self.title.strip() or any(ord(c) < 32 for c in self.title):
            raise ValueError('Frame title must be a nonempty single line')
        self.title = self.title.strip()
        return self


class FrameTitles(StrictModel):
    titles: list[FrameTitle] = Field(min_length=1, max_length=12)


def title_map(value, frames):
    titles = FrameTitles.model_validate(value).titles
    expected = {frame['frame_id'] for frame in frames}
    if len(titles) != len(expected) or {title.frame_id for title in titles} != expected:
        raise ValueError('标题必须逐一覆盖本批 frame_id，不得遗漏、重复或添加页面')
    return {title.frame_id: title.title for title in titles}


def generate_frame_titles(pipeline, frames):
    """Cache by actual page content, so repagination retitles only changed pages."""
    prompt = (Path(__file__).parent / 'prompts' / 'beamer_frame_titles.md').read_text(encoding='utf-8')
    result = {}
    pending = []
    for frame in frames:
        identity = digest({'plan_hash': pipeline.run['plan']['hash'], 'prompt': prompt,
            'schema': FrameTitles.model_json_schema(),
            'frame': {k: v for k, v in frame.items() if k != 'frame_id'}})
        key = 'beamer.title.' + identity
        cached = pipeline.store.cached_step(pipeline.run['id'], key, identity)
        if cached:
            result[frame['frame_id']] = FrameTitle(frame_id=frame['frame_id'], title=cached['title']).title
        else:
            pending.append((frame, key, identity))
    batches = []
    for item in pending:
        if not batches or len(batches[-1]) >= 12 or sum(len(x[0]['content_tex']) for x in batches[-1]) + len(item[0]['content_tex']) > 24000:
            batches.append([])
        batches[-1].append(item)
    for batch in batches:
        pipeline.stage('BUILDING', 'beamer.frame_titles')
        context = {'document_title': pipeline.run['plan']['title'], 'frames': [f for f, _, _ in batch]}
        for attempt in range(pipeline.settings.max_schema_repair_attempts + 1):
            value = pipeline.provider.generate('beamer_frame_titles', context, FrameTitles)
            with pipeline.store.transaction() as connection:
                pipeline.store.assert_fence(connection, pipeline.job)
            try:
                mapping = title_map(value, context['frames'])
                break
            except ValueError as error:
                if attempt == pipeline.settings.max_schema_repair_attempts:
                    raise AgentError('BEAMER_TITLE_BLOCKED', '逐页标题生成未通过：' + str(error)) from error
                context.update(previous_response=value, repair_issues=[str(error)])
        for frame, key, identity in batch:
            title = mapping[frame['frame_id']]
            pipeline.store.checkpoint(pipeline.job, key, identity, {'title': title})
            result[frame['frame_id']] = title
    return result
