with enriched as (
    select * from {{ ref('int_fixtures_enriched_with_teams') }}
),

final as (
    select
        fixture_id,
        league_id,
        fixture_status,
        fixture_date,
        home_team_name,
        away_team_name,
        home_score,
        away_score,
        total_score,
        is_finished,
        created_at,
        updated_at
    from enriched
)

select * from final
