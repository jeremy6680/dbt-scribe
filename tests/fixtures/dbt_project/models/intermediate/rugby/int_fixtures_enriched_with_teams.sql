with fixtures as (
    select * from {{ ref('stg_api_sports__fixtures') }}
),

teams as (
    select * from {{ ref('stg_api_sports__teams') }}
),

enriched as (
    select
        f.fixture_id,
        f.league_id,
        f.fixture_status,
        f.fixture_date,
        f.home_score,
        f.away_score,
        f.is_finished,
        ht.team_name as home_team_name,
        at.team_name as away_team_name,
        (f.home_score + f.away_score) as total_score,
        f.created_at,
        f.updated_at
    from fixtures f
    left join teams ht on f.home_team_id = ht.team_id
    left join teams at on f.away_team_id = at.team_id
)

select * from enriched
