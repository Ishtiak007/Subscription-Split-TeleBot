"""
Telegram Subscription Split Bot
Manages shared subscriptions and payment tracking for group members
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List
import asyncio
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Data storage file
DATA_FILE = 'subscriptions_data.json'

class SubscriptionManager:
    """Manages subscription data and operations"""
    
    def __init__(self):
        self.data = self.load_data()
    
    def load_data(self) -> Dict:
        """Load data from JSON file"""
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        return {
            'subscriptions': {},
            'groups': {},
            'payments': {}
        }
    
    def save_data(self):
        """Save data to JSON file"""
        with open(DATA_FILE, 'w') as f:
            json.dump(self.data, f, indent=2)
    
    def add_subscription(self, group_id: str, name: str, total_cost: float, members: List[str]):
        """Add a new subscription"""
        sub_id = f"{group_id}_{name}_{datetime.now().timestamp()}"
        cost_per_person = total_cost / len(members)
        
        self.data['subscriptions'][sub_id] = {
            'name': name,
            'group_id': group_id,
            'total_cost': total_cost,
            'members': members,
            'cost_per_person': round(cost_per_person, 2),
            'created_at': datetime.now().isoformat(),
            'next_payment': (datetime.now() + timedelta(days=30)).isoformat()
        }
        
        # Initialize payment status for each member
        for member in members:
            payment_key = f"{sub_id}_{member}"
            self.data['payments'][payment_key] = {
                'paid': False,
                'last_payment': None
            }
        
        self.save_data()
        return sub_id
    
    def get_subscriptions(self, group_id: str) -> List[Dict]:
        """Get all subscriptions for a group"""
        return [
            {**sub, 'id': sub_id}
            for sub_id, sub in self.data['subscriptions'].items()
            if sub['group_id'] == str(group_id)
        ]
    
    def get_member_dues(self, group_id: str, member_id: str) -> List[Dict]:
        """Get payment dues for a specific member"""
        dues = []
        for sub_id, sub in self.data['subscriptions'].items():
            if sub['group_id'] == str(group_id) and str(member_id) in sub['members']:
                payment_key = f"{sub_id}_{member_id}"
                payment_status = self.data['payments'].get(payment_key, {})
                dues.append({
                    'subscription': sub['name'],
                    'amount': sub['cost_per_person'],
                    'paid': payment_status.get('paid', False),
                    'next_payment': sub['next_payment']
                })
        return dues
    
    def mark_payment(self, sub_id: str, member_id: str, paid: bool = True):
        """Mark payment status for a member"""
        payment_key = f"{sub_id}_{member_id}"
        if payment_key in self.data['payments']:
            self.data['payments'][payment_key]['paid'] = paid
            if paid:
                self.data['payments'][payment_key]['last_payment'] = datetime.now().isoformat()
            self.save_data()
            return True
        return False
    
    def delete_subscription(self, sub_id: str, group_id: str) -> bool:
        """Delete a subscription"""
        if sub_id in self.data['subscriptions']:
            sub = self.data['subscriptions'][sub_id]
            if sub['group_id'] == str(group_id):
                # Delete associated payments
                for member_id in sub['members']:
                    payment_key = f"{sub_id}_{member_id}"
                    if payment_key in self.data['payments']:
                        del self.data['payments'][payment_key]
                
                # Delete subscription
                del self.data['subscriptions'][sub_id]
                self.save_data()
                return True
        return False

# Initialize manager
manager = SubscriptionManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Welcome message"""
    user = update.effective_user
    
    welcome_text = f"""
👋 Welcome {user.first_name}!

I'm your **Subscription Split Manager** bot. I help you manage shared subscriptions with your group members.

**What I can do:**
• 📝 Track shared subscriptions (Netflix, Spotify, etc.)
• 💰 Split costs automatically among members
• ✅ Track who has paid and who hasn't
• 🔔 Send payment reminders
• 📊 Show detailed payment status

**Quick Start:**
1. Add me to your group
2. Use /add to create a subscription
3. Track payments with /status

**Commands:**
/help - Show all available commands
/add - Create a new subscription
/status - View detailed subscription status
/list - Quick list of all subscriptions
/paid - Mark your payment as completed
/remind - Send payment reminders
/delete - Delete a subscription

Let's get started! 🚀
"""
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - Show all commands"""
    help_text = """
📚 **Subscription Split Bot - All Commands**

**Basic Commands:**
• `/start` - Welcome message and introduction
• `/help` - Show this help message

**Subscription Management:**
• `/add <name> <cost>` - Create new subscription
  Example: `/add Netflix 15.99`

• `/status` - View detailed status of all subscriptions
  Shows: costs, members, payment status

• `/list` - Quick list of all subscriptions
  Shows: subscription names and costs only

• `/delete <subscription_name>` - Delete a subscription
  Example: `/delete Netflix`

**Payment Tracking:**
• `/paid <subscription_name>` - Mark your payment as completed
  Example: `/paid Netflix`

• `/remind` - Send payment reminders to members
  Notifies members who haven't paid yet

**How It Works:**
1️⃣ Create a subscription with /add
2️⃣ Enter member IDs when prompted
3️⃣ Members use /paid to confirm payment
4️⃣ Use /status to track everything

**Tips:**
• Use this bot in group chats for best results
• Make the bot an admin to access member list
• Payments reset monthly automatically

Need help? Just ask! 😊
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def add_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add command - Create subscription"""
    chat = update.effective_chat
    
    # Check if in group
    if chat.type not in ['group', 'supergroup']:
        await update.message.reply_text(
            "⚠️ This command only works in groups!\n"
            "Please add me to a group first."
        )
        return
    
    # Parse arguments
    if len(context.args) < 2:
        await update.message.reply_text(
            "**Usage:** `/add <name> <total_cost>`\n\n"
            "**Example:** `/add Netflix 15.99`\n\n"
            "This will create a new subscription that will be split among members.",
            parse_mode='Markdown'
        )
        return
    
    name = context.args[0]
    try:
        total_cost = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid cost. Please enter a number.")
        return
    
    await update.message.reply_text(
        f"📝 **Creating subscription:** {name}\n"
        f"💰 **Total Cost:** ${total_cost}\n\n"
        f"Now, please reply with member user IDs separated by spaces.\n\n"
        f"**Example:** `123456789 987654321`\n"
        f"Or mention members with their @username\n\n"
        f"💡 **Tip:** Get user IDs by forwarding their messages to @userinfobot",
        parse_mode='Markdown'
    )
    
    # Store context for next message
    context.user_data['pending_subscription'] = {
        'name': name,
        'cost': total_cost,
        'group_id': chat.id
    }

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - View all subscriptions with detailed info"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == 'private':
        await update.message.reply_text(
            "ℹ️ Please use this command in your group to see payment status."
        )
        return
    
    # Get subscriptions for this group
    subscriptions = manager.get_subscriptions(chat.id)
    
    if not subscriptions:
        await update.message.reply_text(
            "📭 No subscriptions found for this group.\n\n"
            "Use `/add <name> <cost>` to create one!\n"
            "Example: `/add Netflix 15.99`",
            parse_mode='Markdown'
        )
        return
    
    # Build detailed status message
    status_text = "📊 **Subscription Status - Detailed View**\n"
    status_text += "=" * 40 + "\n\n"
    
    total_monthly = 0
    
    for sub in subscriptions:
        total_monthly += sub['total_cost']
        status_text += f"**🎬 {sub['name']}**\n"
        status_text += f"💵 Total Cost: ${sub['total_cost']}\n"
        status_text += f"👥 Members: {len(sub['members'])}\n"
        status_text += f"💰 Per Person: ${sub['cost_per_person']}\n"
        status_text += f"📅 Next Payment: {sub['next_payment'][:10]}\n\n"
        
        status_text += "**Payment Status:**\n"
        # Show payment status for each member
        for member_id in sub['members']:
            payment_key = f"{sub['id']}_{member_id}"
            payment = manager.data['payments'].get(payment_key, {})
            
            if payment.get('paid'):
                status_icon = "✅"
                last_payment = payment.get('last_payment', 'N/A')
                if last_payment != 'N/A':
                    last_payment = last_payment[:10]
                status_text += f"{status_icon} User {member_id}: Paid (Last: {last_payment})\n"
            else:
                status_icon = "⏳"
                status_text += f"{status_icon} User {member_id}: **Pending Payment**\n"
        
        status_text += "\n" + "-" * 40 + "\n\n"
    
    status_text += f"💳 **Total Monthly Cost:** ${total_monthly:.2f}\n"
    status_text += f"📝 **Total Subscriptions:** {len(subscriptions)}"
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command - Quick list of subscriptions"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text(
            "ℹ️ Please use this command in your group."
        )
        return
    
    subscriptions = manager.get_subscriptions(chat.id)
    
    if not subscriptions:
        await update.message.reply_text(
            "📭 No subscriptions yet.\n\n"
            "Create one with: `/add Netflix 15.99`",
            parse_mode='Markdown'
        )
        return
    
    # Build quick list
    list_text = "📋 **Quick Subscription List**\n\n"
    
    total_cost = 0
    for i, sub in enumerate(subscriptions, 1):
        total_cost += sub['total_cost']
        
        # Count paid members
        paid_count = 0
        for member_id in sub['members']:
            payment_key = f"{sub['id']}_{member_id}"
            payment = manager.data['payments'].get(payment_key, {})
            if payment.get('paid'):
                paid_count += 1
        
        payment_status = f"{paid_count}/{len(sub['members'])} paid"
        
        list_text += f"{i}. **{sub['name']}**\n"
        list_text += f"   💰 ${sub['cost_per_person']}/person | {payment_status}\n\n"
    
    list_text += f"**Total:** ${total_cost:.2f}/month\n\n"
    list_text += "Use `/status` for detailed view"
    
    await update.message.reply_text(list_text, parse_mode='Markdown')

async def paid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /paid command - Mark as paid"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == 'private':
        await update.message.reply_text(
            "ℹ️ This command only works in groups."
        )
        return
    
    # Check if subscription name provided
    if len(context.args) < 1:
        await update.message.reply_text(
            "**Usage:** `/paid <subscription_name>`\n\n"
            "**Example:** `/paid Netflix`\n\n"
            "Use `/list` to see all subscriptions.",
            parse_mode='Markdown'
        )
        return
    
    sub_name = context.args[0]
    subscriptions = manager.get_subscriptions(chat.id)
    
    # Find matching subscription
    matching_sub = None
    for sub in subscriptions:
        if sub['name'].lower() == sub_name.lower():
            matching_sub = sub
            break
    
    if not matching_sub:
        await update.message.reply_text(
            f"❌ Subscription '{sub_name}' not found.\n\n"
            f"Use `/list` to see all subscriptions.",
            parse_mode='Markdown'
        )
        return
    
    # Check if user is a member
    if str(user.id) not in matching_sub['members']:
        await update.message.reply_text(
            f"⚠️ You're not a member of the {matching_sub['name']} subscription."
        )
        return
    
    # Mark as paid
    success = manager.mark_payment(matching_sub['id'], str(user.id), True)
    
    if success:
        await update.message.reply_text(
            f"✅ **Payment Confirmed!**\n\n"
            f"Thank you {user.first_name}!\n"
            f"Your payment for **{matching_sub['name']}** (${matching_sub['cost_per_person']}) "
            f"has been marked as paid.\n\n"
            f"Use `/status` to see updated status.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Error marking payment. Please try again.")

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remind command - Send payment reminders"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text(
            "ℹ️ This command only works in groups."
        )
        return
    
    subscriptions = manager.get_subscriptions(chat.id)
    
    if not subscriptions:
        await update.message.reply_text(
            "📭 No subscriptions to remind about!\n\n"
            "Create one with `/add <name> <cost>`",
            parse_mode='Markdown'
        )
        return
    
    # Build reminder message
    reminder_text = "🔔 **Payment Reminder**\n\n"
    reminder_text += "Hey everyone! Here's a friendly reminder about pending payments:\n\n"
    
    has_pending = False
    
    for sub in subscriptions:
        # Check who hasn't paid
        pending_members = []
        for member_id in sub['members']:
            payment_key = f"{sub['id']}_{member_id}"
            payment = manager.data['payments'].get(payment_key, {})
            if not payment.get('paid'):
                pending_members.append(member_id)
        
        if pending_members:
            has_pending = True
            reminder_text += f"**{sub['name']}**\n"
            reminder_text += f"💰 Amount: ${sub['cost_per_person']} per person\n"
            reminder_text += f"📅 Due: {sub['next_payment'][:10]}\n"
            reminder_text += f"⏳ Pending from:\n"
            for member_id in pending_members:
                reminder_text += f"  • User {member_id}\n"
            reminder_text += "\n"
    
    if not has_pending:
        reminder_text = "🎉 **Great news!**\n\n"
        reminder_text += "All payments are up to date! ✅\n\n"
        reminder_text += "Thank you everyone for being on time!"
    else:
        reminder_text += "\n💡 **To mark as paid, use:**\n"
        reminder_text += "`/paid <subscription_name>`\n\n"
        reminder_text += "Thank you! 🙏"
    
    await update.message.reply_text(reminder_text, parse_mode='Markdown')

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /delete command - Delete a subscription"""
    chat = update.effective_chat
    user = update.effective_user
    
    if chat.type == 'private':
        await update.message.reply_text(
            "ℹ️ This command only works in groups."
        )
        return
    
    # Check if user is admin
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            await update.message.reply_text(
                "⚠️ Only group admins can delete subscriptions."
            )
            return
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
    
    # Check if subscription name provided
    if len(context.args) < 1:
        await update.message.reply_text(
            "**Usage:** `/delete <subscription_name>`\n\n"
            "**Example:** `/delete Netflix`\n\n"
            "Use `/list` to see all subscriptions.",
            parse_mode='Markdown'
        )
        return
    
    sub_name = context.args[0]
    subscriptions = manager.get_subscriptions(chat.id)
    
    # Find matching subscription
    matching_sub = None
    for sub in subscriptions:
        if sub['name'].lower() == sub_name.lower():
            matching_sub = sub
            break
    
    if not matching_sub:
        await update.message.reply_text(
            f"❌ Subscription '{sub_name}' not found.\n\n"
            f"Use `/list` to see all subscriptions.",
            parse_mode='Markdown'
        )
        return
    
    # Delete subscription
    success = manager.delete_subscription(matching_sub['id'], chat.id)
    
    if success:
        await update.message.reply_text(
            f"🗑️ **Subscription Deleted**\n\n"
            f"The **{matching_sub['name']}** subscription has been removed.\n"
            f"All associated payment records have been cleared.\n\n"
            f"Use `/list` to see remaining subscriptions.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Error deleting subscription. Please try again.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages (for adding members to subscription)"""
    if 'pending_subscription' in context.user_data:
        pending = context.user_data['pending_subscription']
        
        # Parse member IDs from message
        text = update.message.text
        member_ids = text.split()
        
        if member_ids:
            # Create subscription
            sub_id = manager.add_subscription(
                group_id=pending['group_id'],
                name=pending['name'],
                total_cost=pending['cost'],
                members=member_ids
            )
            
            cost_per_person = pending['cost'] / len(member_ids)
            
            await update.message.reply_text(
                f"✅ **Subscription Created Successfully!**\n\n"
                f"**{pending['name']}**\n"
                f"💰 Total Cost: ${pending['cost']}\n"
                f"👥 Members: {len(member_ids)}\n"
                f"💵 Cost per person: ${cost_per_person:.2f}\n"
                f"📅 Next payment: 30 days from now\n\n"
                f"**Next Steps:**\n"
                f"• Members can mark payments: `/paid {pending['name']}`\n"
                f"• Check status: `/status`\n"
                f"• Send reminders: `/remind`",
                parse_mode='Markdown'
            )
            
            # Clear pending data
            del context.user_data['pending_subscription']
        else:
            await update.message.reply_text(
                "❌ No valid member IDs found. Please try again.\n\n"
                "Send member IDs separated by spaces."
            )

def main():
    """Start the bot"""
    # Get token from environment variable
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("\nTo set it:")
        print("  Linux/Mac: export TELEGRAM_BOT_TOKEN='your_token_here'")
        print("  Windows: set TELEGRAM_BOT_TOKEN=your_token_here")
        print("\nOr create a .env file with:")
        print("  TELEGRAM_BOT_TOKEN=your_token_here")
        return
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("add", add_subscription))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("paid", paid_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("delete", delete_command))
    
    # Add message handler for regular messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    print("🤖 Bot is starting...")
    print("✅ All commands loaded:")
    print("   /start - Welcome message")
    print("   /help - Show all commands")
    print("   /add - Create subscription")
    print("   /status - View all subscriptions")
    print("   /list - Quick list of subscriptions")
    print("   /paid - Mark as paid")
    print("   /remind - Send payment reminders")
    print("   /delete - Delete a subscription")
    print("\nPress Ctrl+C to stop")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()