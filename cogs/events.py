"""
Dredd, discord bot
Copyright (C) 2020 Moksej
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.
You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import discord
import os
import datetime
import json
import traceback
from discord.ext import commands
from discord.utils import escape_markdown
from utils import default, btime
from utils.default import timeago
from datetime import datetime
from db import emotes


class Events(commands.Cog, name="Events", command_attrs=dict(hidden=True)):
    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
    
    async def bot_check(self, ctx):
        moks = self.bot.get_user(345457928972533773)
        if ctx.author == moks:
            return True
        try:
            if self.bot.blacklisted_users[ctx.author.id] == ['No reason']:
                reasons = ''
            elif self.bot.blacklisted_users[ctx.author.id] != ['No reason']:
                reason = "".join(self.bot.blacklisted_users[ctx.author.id])
                reasons = f"**Reason:** {reason}\n"
        except KeyError:
            return True
        
        support = self.bot.support

        if self.bot.blacklisted_users[ctx.author.id]:
            print(f"{ctx.author} attempted to use my commands, but was blocked because of the blacklist.\n[REASON] {reason}")
            for u, g, t in self.bot.informed_times:
                if u == ctx.author.id and g == ctx.guild.id:
                    if t >= 1:
                        return False 
            e = discord.Embed(color=self.bot.error_color, title=f"{emotes.blacklisted} Error occured!", description=f"Uh oh! Looks like you are blacklisted from me and cannot execute my commands!\n{reasons}\n[Join support server to learn more]({support})")
            await ctx.send(embed=e, delete_after=15)
            self.bot.informed_times.append((ctx.author.id, ctx.guild.id, 1))
            return False
        return True

    @commands.Cog.listener()
    async def on_ready(self):
        m = "Logged in as:"
        m += "\nName: {0} ({0.id})".format(self.bot.user)
        m += f"\nTime taken to boot: {btime.human_timedelta(self.bot.uptime, suffix=None)}"
        print(m)
        await self.bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.watching,
                                          name="-help")
            )
        for g in self.bot.blacklisted_guilds:
            d = self.bot.get_guild(g)
            try:
                await d.leave()
                print(f"[BLACKLIST ACTION] Left blacklisted guild ({d.id})")
            except:
                pass
        #await self.bot.change_presence(status='idle', activity=discord.Activity(type=discord.ActivityType.playing, name=f"Dredd's rewrite"))
    

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        
        # Check if guild is blacklisted before continuing
        reason = await self.bot.db.fetchval("SELECT reason FROM blockedguilds WHERE guild_id = $1", guild.id)
        support = self.bot.support

        # If it is blacklisted, log it.
        try:
            if self.bot.blacklisted_guilds[guild.id]:
                try:
                    to_send = sorted([chan for chan in guild.channels if chan.permissions_for(
                        guild.me).send_messages and isinstance(chan, discord.TextChannel)], key=lambda x: x.position)[0]
                except IndexError:
                    pass
                else:
                    e = discord.Embed(color=self.bot.logembed_color, title=f"{emotes.blacklisted} Blacklist error!", description=f"Looks like the guild you've tried inviting me to is blacklisted and I cannot join it.\nBlacklist reason: {reason}\n\n[Join support server for more information]({support})")
                    await to_send.send(embed=e)
                    await guild.leave()
                
                # Send it to the log channel
                chan = self.bot.get_channel(676419533971652633)
                modid = await self.bot.db.fetchval("SELECT dev FROM blockedguilds WHERE guild_id = $1", guild.id)
                mod = self.bot.get_user(modid)
                e = discord.Embed(color=self.bot.logembed_color, title=f"{emotes.blacklisted} Attempted Invite", timestamp=datetime.utcnow(),
                                description=f"A blacklisted guild attempted to invite me.\n**Guild name:** {guild.name}\n**Guild ID:** {guild.id}\n**Guild Owner:** {guild.owner}\n**Guild size:** {len(guild.members)-1}\n**Blacklisted by:** {mod}\n**Blacklist reason:** {reason}")
                e.set_thumbnail(url=guild.icon_url)
                return await chan.send(embed=e)
        except KeyError:
            pass
        
        # Guild is not blacklisted!
        # Insert guild's data to the database
        prefix = '-'
        await self.bot.db.execute("INSERT INTO guilds(guild_id, prefix) VALUES ($1, $2)", guild.id, prefix)
        await self.bot.db.execute("INSERT INTO raidmode(guild_id, raidmode, dm) VALUES ($1, $2, $3)", guild.id, False, True)
        self.bot.prefixes[guild.id] = prefix
        
        Zenpa = self.bot.get_user(373863656607318018)
        Moksej = self.bot.get_user(345457928972533773)
        support = self.bot.support
        try:
            to_send = sorted([chan for chan in guild.channels if chan.permissions_for(
                guild.me).send_messages and isinstance(chan, discord.TextChannel)], key=lambda x: x.position)[0]
        except IndexError:
            pass
        else:
            if to_send.permissions_for(guild.me).embed_links:  # We can embed!
                e = discord.Embed(
                    color=self.bot.join_color, title="A cool bot has spawned in!")
                e.description = f"Thank you for adding me to this server! If you'll have any questions you can contact `{Moksej}` or `{Zenpa}`. You can also [join support server]({support})\nTo get started, you can use my commands with my prefix: `{prefix}`, and you can also change the prefix by typing `{prefix}prefix [new prefix]`"
                await to_send.send(embed=e)
            else:  # We were invited without embed perms...
                msg = f"Thank you for adding me to this server! If you'll have any questions you can contact `{Moksej}` or `{Zenpa}`. You can also join support server: {support}\nTo get started, you can use my commands with my prefix: `{prefix}`, and you can also change the prefix by typing `{prefix}prefix [new prefix]`"
                await to_send.send(msg)

        # Log the join
        logchannel = self.bot.get_channel(675333016066719744) 

        members = len(guild.members)
        bots = len([x for x in guild.members if x.bot])
        tch = len(guild.text_channels)
        vch = len(guild.voice_channels)

        ratio = f'{int(100 / members * bots)}'

        embed = discord.Embed(color=self.bot.logging_color, title="I've joined a guild",
                              description="I've joined a new guild. Informing you for safety reasons")
        embed.set_thumbnail(url=guild.icon_url)
        embed.add_field(name="__**General Info**__",
                        value=f"**Guild name:** {guild.name}\n**Guild ID:** {guild.id}\n**Guild owner:** {guild.owner}\n**Guild owner ID:** {guild.owner.id}\n**Guild created:** {default.date(guild.created_at)} ({default.timeago(datetime.utcnow() - guild.created_at)})\n**Member count:** {members-1} (Bots / Users ratio: {ratio}%)\n**Text channels:** {tch}\n**Voice channels:** {vch}", inline=False)
        await logchannel.send(embed=embed)



    @commands.Cog.listener()
    async def on_guild_remove(self, guild):

        # Delete guild data from the database
        # await self.bot.db.execute("DELETE FROM automods WHERE guild_id = $1", guild.id)
        await self.bot.db.execute("DELETE FROM guilds WHERE guild_id = $1", guild.id)
        self.bot.prefixes.pop(guild.id)

        # Log the leave
        members = len(guild.members)
        logchannel = self.bot.get_channel(675333016066719744)

        e = discord.Embed(color=self.bot.logging_color, title='I\'ve left the guild...', description=f"**Guild name:** {guild.name}\n**Member count:** {members}")
        await logchannel.send(embed=e)
    
    
    @commands.Cog.listener()
    async def on_message(self, message):
        # We don't want to listen to bots
        if message.author.bot:
            return

        # We dont want to listen to commands
        try:
            ctx = await self.bot.get_context(message)
            if ctx.valid:
                return
        except:
            return

        # Something happened in DM's
        if message.guild is None:
            blacklist = await self.bot.db.fetchval("SELECT * FROM blacklist WHERE user_id = $1", message.author.id)
            dm_blacklist = await self.bot.db.fetchval("SELECT * FROM dm_black WHERE user_id = $1", message.author.id)
            if blacklist:
                return
            
            if dm_blacklist:
                return

            if message.content.lower().startswith("-"):
                return await message.author.send("You can use my commands in DM with prefix `!`.")

            # They DM'ed the bot
            logchannel = self.bot.get_channel(674929832596865045)
            msgembed = discord.Embed(
                title="Received new Direct Message:", description=message.content, color=self.bot.log_color, timestamp=datetime.utcnow())
            msgembed.set_author(name=message.author,
                                icon_url=message.author.avatar_url)
            # They've sent a image/gif/file
            if message.attachments:
                attachment_url = message.attachments[0].url
                msgembed.set_image(url=attachment_url)
            msgembed.set_footer(text=f"User ID: {message.author.id}")
            await logchannel.send(embed=msgembed)


    @commands.Cog.listener('on_message')
    async def afk_check(self, message):
        if message.guild is None:
            return
        
        if message.author.bot:
            return
        
        guild_afk = []
        for user, guild, msg, time in self.bot.afk_users:
            afkmsg = ""
            if message.author.id == user and message.guild.id == guild:
                ctx = await self.bot.get_context(message)
                if ctx.valid:
                    return              
                await message.channel.send(f"Welcome back {message.author.mention}! Removing your AFK state.", delete_after=20)
                self.bot.afk_users.remove((user, guild, msg, time))
                return await self.bot.db.execute("DELETE FROM userafk WHERE user_id = $1 AND guild_id = $2", message.author.id, message.guild.id)
                
            for userids in message.mentions:
                if userids.id == user:
                    usere = message.guild.get_member(userids)
                    afkmsg += f"{usere} is afk:"
    
            if afkmsg and message.guild.id == guild:
                afkmsg = afkmsg.strip()
                if '\n' in afkmsg:
                    afkmsg = "\n" + afkmsg
                note = msg
                time = time
                afkuser = message.guild.get_member(user)
                try:
                    await message.channel.send(f'{message.author.mention}, **{escape_markdown(afkuser.display_name, as_needed=True)}** went AFK **{timeago(time)}**, but he left you a note: **{escape_markdown(note, as_needed=True)}**', delete_after=30, allowed_mentions=discord.AllowedMentions(roles=False, everyone=False, users=True))
                except discord.HTTPException:
                    try:
                        await message.author.send(f"Yo, **{escape_markdown(afkuser.display_name, as_needed=True)}** went AFK **{timeago(time)}**, but he left you a note: **{escape_markdown(note, as_needed=True)}**")
                    except discord.Forbidden:
                        return
    
    @commands.Cog.listener('on_message')
    async def lmao_count(self, message):

        ice = self.bot.get_user(302604426781261824)
        if "lmao" in message.content.lower():
            if not message.author == ice:
                return
            await self.bot.db.execute('UPDATE lmaocount SET count = count + 1 WHERE user_id = $1', message.author.id)
            
        if "lmfao" in message.content.lower():
            if not message.author == ice:
                return
            await self.bot.db.execute('UPDATE lmaocount SET lf = lf + 1 WHERE user_id = $1', message.author.id)


    @commands.Cog.listener('on_message')
    async def del_staff_ping(self, message):
        moksej = self.bot.get_user(345457928972533773)
        if message.channel.id == 603800402013585408 and message.author.id == 568254611354419211:
            if "added bot" in message.content.lower():
                await moksej.send(f"New bot added {message.jump_url}")
            if "resubmitted bot" in message.content.lower():
                await moksej.send(f"Bot resubmitted {message.jump_url}")

    @commands.Cog.listener('on_member_update')
    async def nicknames_logging(self, before, after):
        if before.bot:
            return
        nicks_opout = await self.bot.db.fetchval("SELECT user_id FROM nicks_op_out WHERE user_id = $1", before.id)
        
        if before.nick != after.nick and nicks_opout is None:
            if before.nick is None:
                nick = before.name
            elif before.nick:
                nick = before.nick
            await self.bot.db.execute("INSERT INTO nicknames(user_id, guild_id, nickname, time) VALUES ($1, $2, $3, $4)", before.id, before.guild.id, nick, datetime.utcnow())
                

def setup(bot):
    bot.add_cog(Events(bot))
