# Future Ideas

## Saved Search Email Notifications
- Subscribe form at top of listings: enter email, saves current filter state
- Backend options: Supabase free tier for subscription storage, Resend/SendGrid for sending
- GitHub Action reads subscriptions after daily scrape, matches against new data, sends bare-bones email with: movie names, ticket links, Letterboxd descriptions, screening times
- Filter state serialized as JSON blob alongside email
- Alternative: Google Form -> Sheet as store + Gmail SMTP via Action

## "Surprise Me" Button
- Picks a random screening from whatever's currently filtered
- Good for indecisive moviegoers

## "Films Showing Near Me"
- Use browser geolocation instead of draw-on-map for quicker location filter

## Director Deep-Link
- Click a director name to instantly filter to all their screenings

## Remove Sold Out Listings
- Detect sold-out screenings during scraping (check ticket links for "sold out" text)
- Filter them out so users only see available screenings

## Price as a Filter
- Hardcoded per-theater pricing (Film Forum $17, Metrograph $18, Anthology $12, etc.)
- Display in cards, add min/max price filter
- Could also try scraping per-showing prices from theater pages
