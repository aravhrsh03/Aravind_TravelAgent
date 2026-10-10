# Dataset Details

## 1. Source datasets

| | UCI #485 Travel Review Ratings | UCI #484 Travel Reviews (TripAdvisor) |
|---|---|---|
| Link | https://archive.ics.uci.edu/dataset/485/tarvel+review+ratings | https://archive.ics.uci.edu/dataset/484/travel+reviews |
| Origin | Google reviews of attractions across Europe | TripAdvisor reviews, East Asia |
| Records | 5,456 users | 980 users |
| Format | CSV: `User`, 24 category columns (average rating 0-5) | CSV: `User ID`, 10 category columns (average rating 0-4) |
| Categories | churches, resorts, beaches, parks, theatres, museums, malls, zoo, restaurants, pubs/bars, local services, burger/pizza shops, hotels, juice bars, art galleries, dance clubs, swimming pools, gyms, bakeries, beauty & spas, cafes, view points, monuments, gardens | art galleries, dance clubs, juice bars, restaurants, museums, resorts, parks/picnic spots, beaches, theaters, religious institutions |
| File in repo | `data/raw/uci485_google_review_ratings.csv` | `data/raw/uci484_tripadvisor_review.csv` |

> Note: the brief's "primary link" points to UCI #485 under the name "TripAdvisor Travel Review Ratings", which is the
> name of UCI #484. We use both. The alternative links (hotel reviews / OULAD) were not used: OULAD is an education
> dataset, and the hotel review sets need a Kaggle login.

Supporting knowledge base: `data/catalog/destinations.json` is a hand-curated catalog of **32 destinations**
(9 regions). Each has 8 preference-dimension strengths, per-person daily cost by budget tier, best months,
minimum/ideal/maximum days, and 7-10 costed activities. These are reference estimates, not live prices.

## 2. Why preprocessing includes simulation

The brief's key fields are `user_id, destination, category, rating, review_text, travel_type, visit_date`. Neither
UCI dataset has review text, destinations, travel type or dates; they hold only *user x category average ratings*.
They do carry real preference signal from 6,436 travelers, so we build the corpus in three steps.

1. **Category mapping → Traveler DNA.** Source categories are mapped to 8 dimensions (beach, culture, food,
   nightlife, nature, shopping, wellness, family). For example, culture = mean(churches, theatres, museums, art
   galleries, monuments). Each traveler's vector is turned into *relative* interest with a z-score then a sigmoid, so
   it captures what the person likes *more than they usually do*. #484 has no shopping category, so it is imputed
   from the traveler's overall activity level plus noise.
2. **Trip simulation** (`src/services/dataset_builder.py`, seed 42). For each traveler (plus a second trip for 20%):
   travel type and budget tier are sampled based on their DNA. The destination is chosen by preference match 75% of
   the time and at random 25% of the time, which creates the poorly matched trips the model needs as negative
   examples. Month is in season 65% of the time, and days ≈ the destination's ideal length ± noise.
3. **Rating and review text from one model.** A transparent satisfaction model scores each trip:
   `3.2 + preference fit + season + budget pressure + duration fit + party fit + N(0, 0.45)`, clipped to 1-5. The
   review text is then composed from the *same* factors: activity sentences turn negative when the traveler dislikes
   that dimension, there are weather complaints off-season, cost complaints on a budget tier at expensive places, and
   so on. Text, rating and metadata therefore agree, which is what makes semantic retrieval meaningful.

## 3. Cleaning (applied to any corpus, generated or external)

Dedupe on (user, destination, date, text) · whitespace normalization · drop reviews under 20 characters · coerce
rating to an integer 1-5 · normalize `travel_type` to {solo, couple, family, friends, business}.

## 4. Output corpus: `data/processed/travel_experiences.csv` (7,712 rows)

| Field | Example | Notes |
|---|---|---|
| review_id | R00099 | primary key, used for citations |
| user_id | G1234 / T56 | G = UCI #485 traveler, T = UCI #484 traveler |
| destination, country, region | Phuket, Thailand, Southeast Asia | |
| category | beach | dominant dimension of the trip (traveler interest x destination strength) |
| rating | 1-5 | distribution: 1★ 43 · 2★ 399 · 3★ 1,872 · 4★ 3,594 · 5★ 1,804 (mean 3.87) |
| title, review_text | "Great trip", "Spent 5 days exploring…" | 60-120 words |
| travel_type | couple | solo / couple / family / friends / business |
| visit_date, visit_month | 2024-02-18, 2 | 2019-2025 |
| duration_days | 5 | 2-16 |
| budget_tier, spend_per_day_usd, trip_cost_usd | mid, 94.2, 471 | |
| activities | "Phi Phi Islands speedboat tour \| Thai cooking class" | |
| home_region, source_dataset | South Asia, uci485_google | |

Also produced: `traveler_profiles.csv` (6,436 Traveler DNA vectors, used by Travel Twins) and a 200-row sample in
`data/sample_data/travel_experiences_sample.csv`.

## 5. Purpose in the system

Semantic and hybrid retrieval of similar trips · metadata filtering (destination, travel type, rating, budget,
month, duration) · preference classification and scoring · Travel Twins collaborative signal · training data for
the suitability model · evidence for itinerary citations.

## 6. Limitations

- Review text is template-composed, so its vocabulary is narrower than real reviews. This is why the cross-encoder
  adds little on top of hybrid retrieval in our ablation.
- Ratings come from a known function, so the suitability model partly learns that function back (logistic regression
  scores almost as well as the boosted trees). The pipeline is built to swap in real data: `load_external_experiences()`
  accepts any CSV with the key fields, and everything downstream is unchanged.
