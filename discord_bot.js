const { Client, GatewayIntentBits } = require('discord.js');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

// Read from .env if present
let envToken = process.env.DISCORD_BOT_TOKEN;
const envPath = path.join(__dirname, '.env');
if (!envToken && fs.existsSync(envPath)) {
    const envContent = fs.readFileSync(envPath, 'utf8');
    const match = envContent.match(/DISCORD_BOT_TOKEN\s*=\s*(["']?)([^"'\r\n]+)\1/);
    if (match) {
        envToken = match[2].trim();
    }
}

// YAHAN APNA DISCORD BOT TOKEN PASTE KAREIN (ya .env file mein DISCORD_BOT_TOKEN likhein)
const token = envToken || 'YOUR_DISCORD_BOT_TOKEN_HERE';

// Discord client setup (Intents batate hain ke bot kya kya kar sakta hai)
const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent
    ]
});

client.on('ready', () => {
    console.log(`🤖 Logged in as ${client.user.tag}!`);
    console.log('Discord Bot is ready to receive commands.');
});

// Jab bhi koi message aaye
client.on('messageCreate', (message) => {
    // Agar message kisi dusre bot ne bheja hai, toh ignore karo
    if (message.author.bot) return;

    // Check karo agar message '!analyze' se shuru ho raha hai
    if (message.content.startsWith('!analyze ')) {
        // '!analyze OGDC' mein se 'OGDC' ko nikalna
        const parts = message.content.trim().split(/\s+/);
        if (parts.length < 2) {
            return message.reply('❌ Please provide a symbol. Example: `!analyze OGDC`');
        }
        const symbol = parts[1].toUpperCase();
        
        message.reply(`⏳ Fetching data and generating AI report for **${symbol}**...\nPlease wait...`);

        // Python script ko apne system par run karna
        exec(`python psx_data_fetcher.py ${symbol}`, { maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
            if (error) {
                console.error(`Error: ${error.message}`);
                return message.reply(`❌ Error analyzing ${symbol}. Please ensure the symbol is correct.`);
            }
            
            // Output ko clean karna (Sirf AI Report ka hissa nikalna)
            const reportSplit = stdout.split("==================================================");
            if (reportSplit.length > 2) {
                const cleanReport = reportSplit[1].trim() + "\n\n" + reportSplit[2].trim();
                // Discord message formatting (Discord limit 2000 chars)
                if (cleanReport.length > 1950) {
                    message.reply(`\`\`\`\n${cleanReport.substring(0, 1950)}\n\`\`\``);
                } else {
                    message.reply(`\`\`\`\n${cleanReport}\n\`\`\``);
                }
            } else {
                // Agar split fail ho jaye toh raw output bhej do (Discord limit 2000 chars)
                message.reply(`\`\`\`\n${stdout.substring(0, 1900)}\n\`\`\``); 
            }
        });
    }
});

// Token check & Login
if (!token || token === 'YOUR_DISCORD_BOT_TOKEN_HERE') {
    console.error('⚠️ ERROR: Please provide your Discord Bot Token in discord_bot.js or in the .env file!');
    process.exit(1);
}

client.login(token);
