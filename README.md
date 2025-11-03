# Telegram Subscription Split Bot

A Telegram bot to manage shared subscriptions and split costs among group members.

## Features

- 💰 Split subscription costs automatically
- 👥 Work with usernames (no need for user IDs)
- ✅ Track who paid and who hasn't
- 📊 View payment status
- 🔔 Simple payment management

## Commands

- `/start` - Welcome message
- `/add <name> <cost>` - Create new subscription
- `/list` - View all subscriptions with payment status
- `/paid <name>` - Mark your payment as done
- `/delete <name>` - Remove subscription (admin only)

## Deployment on Render

### Step 1: Prepare Your Files

Make sure you have these files:

- `bot.py` - Main bot code
- `requirements.txt` - Python dependencies
- `.env` - Environment variables (you'll add this on Render)

### Step 2: Create GitHub Repository

1. Go to [GitHub](https://github.com) and create a new repository
2. Upload these files:
   - `bot.py`
   - `requirements.txt`
   - `README.md` (this file)
3. Commit and push

### Step 3: Deploy on Render

1. Go to [Render](https://render.com) and sign up/login
2. Click **"New +"** → **"Background Worker"**
3. Connect your GitHub repository
4. Configure:
   - **Name**: `subscription-split-bot` (or any name)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
5. Add Environment Variable:
   - Click **"Add Environment Variable"**
   - **Key**: `TELEGRAM_BOT_TOKEN`
   - **Value**: Your bot token from @BotFather
6. Click **"Create Background Worker"**

### Step 4: Wait for Deployment

- Render will install dependencies and start your bot
- Check logs to ensure it's running
- Look for: "🤖 Bot is starting..."

### Step 5: Test Your Bot

1. Open Telegram
2. Search for your bot
3. Start a conversation: `/start`
4. Add bot to a group
5. Create a subscription: `/add Netflix 15.99`

## Local Development

### Prerequisites

- Python 3.8 or higher
- pip

### Setup

1. Clone the repository:

```bash
git clone <your-repo-url>
cd subscription-split-bot
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create `.env` file:

```bash
cp .env.example .env
```

4. Edit `.env` and add your bot token:

```
TELEGRAM_BOT_TOKEN=your_actual_token_here
```

5. Run the bot:

```bash
python bot.py
```

## Getting Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot`
3. Follow the instructions
4. Copy the token you receive
5. Use it in your `.env` file or Render environment variables

## Usage Example

```
Admin: /add Netflix 15.99
Bot: Now mention the members...

Admin: @john @alice @bob
Bot: ✅ SUBSCRIPTION CREATED!
     Netflix
     💰 Total: $15.99
     👥 Members: @john, @alice, @bob
     💵 Per person: $5.33

John: /paid Netflix
Bot: ✅ PAYMENT CONFIRMED!
     Thank you John!

Admin: /list
Bot: 📋 SUBSCRIPTIONS
     1. Netflix
        💰 $5.33/person ($15.99 total)
        👥 3 members | ⏳ 1/3 paid
        Pending: @alice, @bob
```

## Data Storage

- Data is stored in `subscriptions_data.json`
- On Render, this uses ephemeral storage
- **Important**: Data will be lost if the service restarts
- For permanent storage, consider upgrading to use a database

## Troubleshooting

### Bot not responding

- Check Render logs
- Verify bot token is correct
- Ensure bot is not running elsewhere

### Data lost after restart

- Render's free tier uses ephemeral storage
- Consider using Redis or PostgreSQL for permanent storage
- Or upgrade to persistent disk on Render

### Commands not working

- Make sure bot is admin in group (for some features)
- Check if commands are set in @BotFather

## Support

If you encounter issues:

1. Check the logs on Render dashboard
2. Verify your bot token
3. Make sure all files are uploaded correctly

## License

Free to use and modify!

## Contributing

Feel free to submit issues and pull requests!
