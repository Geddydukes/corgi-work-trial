# Frontend - Security Deposit Claims Decision Review

Next.js frontend for reviewing and modifying claim decisions.

## Setup

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Configure API URL (optional, defaults to http://localhost:8000/api/v1) and Drive folder ID (optional, defaults to the shared demo ID):
```bash
# Create .env.local file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1" > .env.local
echo "NEXT_PUBLIC_DRIVE_FOLDER_ID=<your_drive_folder_id>" >> .env.local
```

3. Run development server:
```bash
npm run dev
```

The app will be available at http://localhost:3000

## Features

- Search claims by tracking number
- View decision details and line items
- Toggle line items to include/exclude
- Live total calculation
- Add notes for changed items
- Save changes to database
- User overrides stored separately for rule refinement

## UX Notes

- Long line-item lists are rendered naively (no virtualization); very large claims may benefit from windowing/pagination.
- Error/loading states are minimal in variance/decision views; backend connectivity issues are surfaced, but deeper API errors are only lightly summarized.

## API Endpoints Used

- `POST /api/v1/claims/{tracking_number}/decision` - Get/create decision
- `PATCH /api/v1/claims/{tracking_number}/decision/{decision_id}` - Update decision with user overrides
