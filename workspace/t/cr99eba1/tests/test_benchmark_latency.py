from math_agent.benchmark import request_metrics

def test_early_stream_headers_timing_is_not_reported_as_full_completion():
    events=[{'sequence':1,'type':'provider.request','timestamp':'2026-09-19T00:00:00+00:00','payload':{'role':'writer','streaming':True}},
            {'type':'provider.result','timestamp':'2026-09-19T00:00:00.100+00:00','payload':{'role':'writer','http_status':200,'elapsed_seconds':0.1}},
            {'type':'provider.result','timestamp':'2026-09-19T00:00:12+00:00','payload':{'role':'writer','stream_complete':True}},
            {'type':'provider.result','timestamp':'2026-09-19T00:00:12.050+00:00','payload':{'role':'writer','output_hash':'hash'}}]
    metric=request_metrics(events,1,10)
    request=metric['requests'][0]
    assert metric['known_elapsed_seconds']==12.05
    assert request['original_reported_elapsed_seconds']==0.1
    assert request['elapsed_basis']=='durable_event_wall_time_including_local_validation'

def test_full_provider_timer_takes_precedence_over_event_persistence_delay():
    events=[{'sequence':1,'type':'provider.request','timestamp':'2026-09-19T00:00:00+00:00','payload':{'role':'writer','streaming':True}},
            {'type':'provider.result','timestamp':'2026-09-19T00:00:13+00:00','payload':{'role':'writer','elapsed_seconds':12}},
            {'type':'provider.result','timestamp':'2026-09-19T00:00:14+00:00','payload':{'role':'writer','output_hash':'hash'}}]
    request=request_metrics(events,1,10)['requests'][0]
    assert request['elapsed_seconds']==12
    assert request['elapsed_basis']=='provider_complete_request'
