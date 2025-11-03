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
        # Ensure group_id is string
        group_id = str(group_id)
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

I help you manage shared subscriptions and split costs with your group.

COMMANDS:
/add - Create a subscription
/list - View all subscriptions
/paid - Mark payment as done
/delete - Remove a subscription

Add me to your group and use /add to get started! 🚀

💡 I work with usernames - just mention people with @username!
"""
    
    await update.message.reply_text(welcome_text)

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /debug command - Show debug info (admin only)"""
    chat = update.effective_chat
    user = update.effective_user
    
    # Check if user is admin
    try:
        member = await chat.get_member(user.id)
        if member.status not in ['creator', 'administrator']:
            return
    except Exception:
        return
    
    debug_text = f"DEBUG INFO:\n\n"
    debug_text += f"Chat ID: {chat.id}\n"
    debug_text += f"Chat Type: {chat.type}\n\n"
    
    # Show stored subscriptions
    debug_text += f"STORED SUBSCRIPTIONS:\n"
    all_subs = manager.data.get('subscriptions', {})
    if all_subs:
        for sub_id, sub in all_subs.items():
            debug_text += f"• {sub['name']} (Group: {sub['group_id']})\n"
    else:
        debug_text += "None\n"
    
    debug_text += f"\nTotal subscriptions in DB: {len(all_subs)}"
    
    await update.message.reply_text(debug_text)

async def add_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add command - Create subscription"""
    chat = update.effective_chat
    user = update.effective_user
    
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
        f"Now mention the members (including yourself if needed).\n\n"
        f"**Example:** @john @alice @bob\n\n"
        f"💡 You can also just type usernames: john alice bob",
        
    )
    
    # Store context for next message
    context.user_data['pending_subscription'] = {
        'name': name,
        'cost': total_cost,
        'group_id': chat.id,
        'creator_id': user.id,
        'creator_username': user.username or user.first_name
    }

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command - View all subscriptions with payment status"""
    chat = update.effective_chat
    
    if chat.type == 'private':
        await update.message.reply_text(
            "ℹ️ Please use this command in your group."
        )
        return
    
    logger.info(f"List command called for group {chat.id}")
    subscriptions = manager.get_subscriptions(chat.id)
    logger.info(f"Found {len(subscriptions)} subscriptions")
    
    if not subscriptions:
        await update.message.reply_text(
            "📭 No subscriptions yet.\n\nCreate one with: /add Netflix 15.99"
        )
        return
    
    # Build subscription list with details (plain text, no markdown)
    list_text = "📋 SUBSCRIPTIONS\n\n"
    
    total_cost = 0
    for i, sub in enumerate(subscriptions, 1):
        total_cost += sub['total_cost']
        
        # Count paid members
        paid_count = 0
        pending_members = []
        for member_id in sub['members']:
            payment_key = f"{sub['id']}_{member_id}"
            payment = manager.data['payments'].get(payment_key, {})
            if payment.get('paid'):
                paid_count += 1
            else:
                pending_members.append(member_id)
        
        list_text += f"{i}. {sub['name']}\n"
        list_text += f"   💰 ${sub['cost_per_person']}/person (${sub['total_cost']} total)\n"
        list_text += f"   👥 {len(sub['members'])} members | "
        
        if paid_count == len(sub['members']):
            list_text += "✅ All paid\n"
        else:
            list_text += f"⏳ {paid_count}/{len(sub['members'])} paid\n"
            if pending_members:
                # Format usernames with @
                pending_display = ', '.join(['@'+m for m in pending_members[:3]])
                list_text += f"   Pending: {pending_display}"
                if len(pending_members) > 3:
                    list_text += f" +{len(pending_members)-3} more"
                list_text += "\n"
        
        list_text += f"   📅 Next: {sub['next_payment'][:10]}\n\n"
    
    list_text += f"💳 TOTAL: ${total_cost:.2f}/month"
    
    # Use plain text (no parse_mode) to avoid markdown issues with underscores
    await update.message.reply_text(list_text)

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
            
        )
        return
    
    # Check if user is a member (check by username or user ID fallback)
    user_identifier = user.username if user.username else f"{user.first_name}_{user.id}"
    
    # Check if username matches any member
    is_member = False
    member_key = None
    
    for member in matching_sub['members']:
        # Direct match
        if member.lower() == user_identifier.lower():
            is_member = True
            member_key = member
            break
        # Also check without @ symbol
        if member.lower() == user.username.lower() if user.username else False:
            is_member = True
            member_key = member
            break
    
    if not is_member:
        await update.message.reply_text(
            f"⚠️ You're not a member of the {matching_sub['name']} subscription.\n\n"
            f"Your username: @{user_identifier}\n"
            f"Members: {', '.join(['@'+m for m in matching_sub['members']])}"
        )
        return
    
    # Mark as paid using the member key
    success = manager.mark_payment(matching_sub['id'], member_key, True)
    
    if success:
        await update.message.reply_text(
            f"✅ PAYMENT CONFIRMED!\n\n"
            f"Thank you {user.first_name}!\n"
            f"Your payment for {matching_sub['name']} (${matching_sub['cost_per_person']}) "
            f"has been marked as paid.\n\n"
            f"Use /list to see updated status."
        )
    else:
        await update.message.reply_text("❌ Error marking payment. Please try again.")

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
            f"Use /list to see all subscriptions."
        )
        return
    
    # Delete subscription
    success = manager.delete_subscription(matching_sub['id'], chat.id)
    
    if success:
        await update.message.reply_text(
            f"🗑️ SUBSCRIPTION DELETED\n\n"
            f"The {matching_sub['name']} subscription has been removed.\n"
            f"All payment records have been cleared.\n\n"
            f"Use /list to see remaining subscriptions."
        )
    else:
        await update.message.reply_text("❌ Error deleting subscription. Please try again.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages (for adding members to subscription)"""
    if 'pending_subscription' in context.user_data:
        pending = context.user_data['pending_subscription']
        
        text = update.message.text
        message = update.message
        
        # Extract usernames from mentions (entities)
        member_usernames = []
        
        # Check if message has entities (mentions)
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    # Extract username from @username
                    username = text[entity.offset:entity.offset + entity.length]
                    username = username.replace('@', '')  # Remove @
                    member_usernames.append(username)
                elif entity.type == "text_mention":
                    # User mentioned but doesn't have username, use their name
                    if entity.user.username:
                        member_usernames.append(entity.user.username)
                    else:
                        # Store user ID as fallback for users without username
                        member_usernames.append(f"{entity.user.first_name}_{entity.user.id}")
        
        # Also parse text for usernames (without @)
        words = text.split()
        for word in words:
            clean_word = word.replace('@', '').strip()
            # If it looks like a username (alphanumeric with underscores)
            if clean_word and not clean_word.isdigit() and clean_word not in member_usernames:
                # Simple validation: contains letters
                if any(c.isalpha() for c in clean_word):
                    member_usernames.append(clean_word)
        
        if not member_usernames:
            await update.message.reply_text(
                "❌ No valid members found!\n\n"
                "Please mention members or type their usernames:\n"
                "• With @: `@john @alice @bob`\n"
                "• Without @: `john alice bob`\n\n"
                "You can also directly mention them."
            )
            return
        
        # Remove duplicates while preserving order
        member_usernames = list(dict.fromkeys(member_usernames))
        
        # Create subscription
        sub_id = manager.add_subscription(
            group_id=pending['group_id'],
            name=pending['name'],
            total_cost=pending['cost'],
            members=member_usernames
        )
        
        logger.info(f"Created subscription {sub_id} for group {pending['group_id']} with members: {member_usernames}")
        
        cost_per_person = pending['cost'] / len(member_usernames)
        
        # Build member list for display
        member_display = ', '.join([f"@{m}" for m in member_usernames])
        
        await update.message.reply_text(
            f"✅ SUBSCRIPTION CREATED!\n\n"
            f"{pending['name']}\n"
            f"💰 Total: ${pending['cost']}\n"
            f"👥 Members ({len(member_usernames)}): {member_display}\n"
            f"💵 Per person: ${cost_per_person:.2f}\n"
            f"📅 Next payment: 30 days\n\n"
            f"Members can mark payments: /paid {pending['name']}"
        )
        
        # Clear pending data
        del context.user_data['pending_subscription']

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
    application.add_handler(CommandHandler("debug", debug_command))
    application.add_handler(CommandHandler("add", add_subscription))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("paid", paid_command))
    application.add_handler(CommandHandler("delete", delete_command))
    
    # Add message handler for regular messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    print("🤖 Bot is starting...")
    print("✅ Commands loaded:")
    print("   /start - Welcome message")
    print("   /add - Create subscription")
    print("   /list - View all subscriptions")
    print("   /paid - Mark as paid")
    print("   /delete - Delete subscription")
    print("   /debug - Debug info (admin only)")
    print("\n💡 Now using usernames instead of IDs!")
    print("\nPress Ctrl+C to stop")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()