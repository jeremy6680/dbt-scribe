with source as (
    select * from {{ source('api_sports', 'fixtures') }}
),

renamed as (
    select
        fixture_id,
        league_id,
        home_team_id,
        away_team_id,
        fixture_status,
        fixture_date,
        home_score,
        away_score,
        is_finished,
        created_at,
        updated_at
    from source
)

select * from renamed
