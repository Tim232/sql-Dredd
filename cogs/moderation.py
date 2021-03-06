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
import time
import datetime
import asyncio
import random
import typing
from discord.ext import commands
from datetime import datetime
from utils import btime
from utils.paginator import Pages
from db import emotes
from utils.default import responsible, timetext, date
from io import BytesIO

class BannedMember(commands.Converter):
    async def convert(self, ctx, argument):
        if argument.isdigit():
            member_id = int(argument, base=10)
            try:
                return await ctx.guild.fetch_ban(discord.Object(id=member_id))
            except discord.NotFound:
                raise commands.BadArgument('This member has not been banned before.') from None

        elif not argument.isdigit():
            ban_list = await ctx.guild.bans()
            entity = discord.utils.find(lambda u: str(u.user.name) == argument, ban_list)
            if entity is None:
                raise commands.BadArgument('This member has not been banned before.')
            return entity

class MemberNotFound(Exception):
    pass

class MemberID(commands.Converter):
    async def convert(self, ctx, argument):
        if not argument.isdigit():
            raise commands.BadArgument("User needs to be an ID")
        elif argument.isdigit():
            member_id = int(argument, base=10)
            try:
                ban_check = await ctx.guild.fetch_ban(discord.Object(id=member_id))
                if ban_check:
                    raise commands.BadArgument('This user is already banned.') from None
            except discord.NotFound:
                return type('_Hackban', (), {'id': argument, '__str__': lambda s: s.id})()

class moderation(commands.Cog, name="Moderation"):

    def __init__(self, bot):
        self.bot = bot
        self.big_icon = "https://cdn.discordapp.com/emojis/695710706296815626.png?v=1"
        self.help_icon = "<:bann:695710706296815626>"
        self.bot.embed_color = 0x0058D6

# ! Commands

#########################################################################################################

    async def log_delete(self, ctx, data, messages=None):
        check = await self.bot.db.fetchval("SELECT * FROM msgdelete WHERE guild_id = $1", ctx.guild.id)

        if check is not None:
            channel = await self.bot.db.fetchval("SELECT channel_id FROM msgdelete WHERE guild_id = $1", ctx.guild.id)
            chan = self.bot.get_channel(channel)
            message_history = await chan.send(content='You can either download the logs, or view it in the message below', file=data)
            data = f"<https://txt.discord.website/?txt={chan.id}/{message_history.attachments[0].id}/{ctx.message.id}>"
            #e = discord.Embed(color=self.bot.logging_color, description=f"{messages} messages were deleted by **{ctx.author}**. [View File]({data})")
            text = f"**{messages}** Message(s) were deleted by **{ctx.author}**. You can view those messages here as well: **(BETA)** "
            text += data
            await message_history.edit(content=text)
        else:
            pass

    async def do_removal(self, ctx, limit, predicate, *, before=None, after=None):
        if limit > 2000:
            return await ctx.send("You can purge maximum amount of 2000 messages!")

        if before is None:
            before = ctx.message
        else:
            before = discord.Object(id=before)

        if after is not None:
            after = discord.Object(id=after)
        
        msgs = []
        for message in await ctx.channel.history(limit=limit).flatten():
            msgs.append(f"[{message.created_at}] {message.author} - {message.content}\n")
        msgs.reverse()
        msghis = "".join(msgs)

        try:
            deleted = await ctx.channel.purge(limit=limit, before=before, after=after, check=predicate)
            await self.log_delete(ctx, data=discord.File(BytesIO(("".join(msgs)).encode("utf-8")), filename=f"{ctx.message.id}.txt"), messages=len(deleted))
        except discord.Forbidden as e:
            return await ctx.send("No permissions")
        except discord.HTTPException as e:
            return await ctx.send(f"Looks like you got an error: {e}")

        deleted = len(deleted)
        if deleted == 1:
            messages = f"{emotes.log_msgdelete} Deleted **1** message"
        elif deleted > 1:
            messages = f"{emotes.log_msgdelete} Deleted **{deleted}** messages"

        to_send = '\n'.join(messages)

        if len(to_send) > 2000:

            text = f"{emotes.log_msgdelete} Removed `{deleted}` messages"
            await ctx.send(text, delete_after=10)
        else:
            e = discord.Embed(color=self.bot.embed_color)
            e.description = f"{messages}"
            await ctx.send(embed=e, delete_after=10)

    async def log_mute(self, ctx, member=None, reason=None, timed=None):
        check = await self.bot.db.fetchval("SELECT * FROM moderation WHERE guild_id = $1", ctx.guild.id)

        if check is None:
            return
        elif check is not None:
            channel = await self.bot.db.fetchval("SELECT channel_id FROM moderation WHERE guild_id = $1", ctx.guild.id)
            chan = self.bot.get_channel(channel)

            try:
                case = self.bot.case_num[ctx.guild.id]
            except KeyError:
                self.bot.case_num[ctx.guild.id] = 1

            casenum = self.bot.case_num[ctx.guild.id]

            e = discord.Embed(color=self.bot.logging_color, description=f"{emotes.log_memberedit} **{member}** muted `[#{casenum}]`")
            e.add_field(name="Moderator:", value=f"{ctx.author} ({ctx.author.id})", inline=False)
            e.add_field(name="Reason:", value=f"{reason}")
            if timed:
                e.add_field(name="Duration:", value=f"{timed}")
            e.set_thumbnail(url=member.avatar_url_as(format='png'))
            e.set_footer(text=f"Member ID: {member.id}")

            await chan.send(embed=e)
            self.bot.case_num[ctx.guild.id] += 1
            await self.bot.db.execute("UPDATE modlog SET case_num = case_num + 1 WHERE guild_id = $1", ctx.guild.id)
    
    async def log_unmute(self, ctx, member=None, reason=None):
        check = await self.bot.db.fetchval("SELECT * FROM moderation WHERE guild_id = $1", ctx.guild.id)

        if check is None:
            return
        elif check is not None:
            channel = await self.bot.db.fetchval("SELECT channel_id FROM moderation WHERE guild_id = $1", ctx.guild.id)
            chan = self.bot.get_channel(channel)

            try:
                case = self.bot.case_num[ctx.guild.id]
            except KeyError:
                self.bot.case_num[ctx.guild.id] = 1

            casenum = self.bot.case_num[ctx.guild.id]

            e = discord.Embed(color=self.bot.logging_color, description=f"{emotes.log_memberedit} **{member}** unmuted `[#{casenum}]`")
            e.add_field(name="Moderator:", value=f"{ctx.author} ({ctx.author.id})", inline=False)
            e.add_field(name="Reason:", value=f"{reason}", inline=False)
            e.set_thumbnail(url=member.avatar_url_as(format='png'))
            e.set_footer(text=f"Member ID: {member.id}")

            await chan.send(embed=e)
            self.bot.case_num[ctx.guild.id] += 1
            await self.bot.db.execute("UPDATE modlog SET case_num = case_num + 1 WHERE guild_id = $1", ctx.guild.id)

    async def cog_check(self, ctx):
        if ctx.guild is None:
            return False
        return True


#########################################################################################################

    @commands.command(brief="Change someones nickname", description="Change or remove anyones nickname", aliases=["nick"])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def setnick(self, ctx, member: discord.Member, *, name: str = None):
        """ Change someone's nickname """
        
        
        try:
            if member.top_role.position > ctx.author.top_role.position:
                return await ctx.send("You can't change nickname of the member that is above you")
            elif member.top_role.position >= ctx.guild.me.top_role.position:
                return await ctx.send(f"I was unable to change {member.name}'s nickname")
            if name and len(name) > 32:
                return await ctx.send(f"{emotes.red_mark} Nickname is too long! You can't have nicknames longer than 32 characters")
            await member.edit(nick=name)
            if name is not None:
                emb = discord.Embed(color=self.bot.embed_color, description=f"{emotes.white_mark} Changed **{member.name}'s** nickname to **{name}**.")
                return await ctx.send(embed=emb)
            elif name is None:
                emb = discord.Embed(color=self.bot.embed_color, description=f"{emotes.white_mark} Removed **{member.name}'s** nickname")
                return await ctx.send(embed=emb)
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to change **{member}**'s nickname.")

    @commands.command(brief="Kick members", description="Kick someone from the server")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True, manage_messages=True)
    async def kick(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = None):
        """
        Kicks member from server.
        You can also provide multiple members to kick.
        """
        try:
            total = len(members)

            if total == 0:
                return await ctx.send("Please provide member(s) to kick.")
            
            
            failed = 0
            for member in members:
                if member.top_role.position >= ctx.author.top_role.position:
                    failed += 1
                    continue
                elif member.top_role.position >= ctx.guild.me.top_role.position:
                    failed += 1
                    continue
                elif member == ctx.author:
                    failed += 1
                    continue
                try:
                    await member.guild.kick(member, reason=responsible(ctx.author, reason))
                except discord.HTTPException:
                    failed += 1

            if failed == 0:
                await ctx.send(f"{emotes.white_mark} Succesfully kicked **{total}** members.")
            else:
                await ctx.send(f"Successfully kicked **{total - failed}/{total}** members.")
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to kick members.")

    @commands.command(brief="Ban members", description="Ban someone from the server")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True, manage_messages=True)
    async def ban(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = None):
        """
        Ban member from the server.
        You can also provide multiple members to ban.
        """

        if len(members) == 0:
            raise commands.BadArgument("You're missing an argument - **members**") from None

        try:
            total = len(members)
            

            failed = 0
            for member in members:
                if member.top_role.position >= ctx.author.top_role.position:
                    failed += 1
                    continue
                elif member.top_role.position >= ctx.guild.me.top_role.position:
                    failed += 1
                    continue
                elif member == ctx.author:
                    failed += 1
                    continue
                try:
                    await member.guild.ban(member, reason=responsible(ctx.author, reason))
                except discord.HTTPException:
                    failed += 1

            if failed == 0:
                await ctx.send(f"{emotes.white_mark} Succesfully banned **{total}** members.")
            else:
                await ctx.send(f"Successfully banned **{total - failed}/{total}** members.")
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to ban members.")

    @commands.command(brief='Ban members that are not in the server')
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def hackban(self, ctx, user: MemberID, *, reason: str = None):
        """ Ban a user that isn't in this server """

        try:
            try:
                m = await commands.MemberConverter().convert(ctx, str(user))
                if m is not None:
                    return await ctx.send(f"{emotes.warning} Hack-ban is to ban users that are not in this server.")
            except:
                pass
            await ctx.guild.ban(user, reason=responsible(ctx.author, reason))
            await ctx.send(f"{emotes.white_mark} Banned **{await self.bot.fetch_user(user)}** for `{reason}`")
        except Exception as e:
            print(e)
            return await ctx.send(f"{emotes.error} Something failed!")


    @commands.command(brief="Unban members", description="Unban someone from the server")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True, manage_messages=True)
    async def unban(self, ctx, user: BannedMember, *, reason: str=None):
        """
        Unbans user from server
        """
        try:
            await ctx.message.delete()
            await ctx.guild.unban(user.user, reason=responsible(ctx.author, reason))
            await ctx.send(f"{emotes.white_mark} **{user.user}** was unbanned successfully, with a reason: ``{reason}``", delete_after=15)
        except Exception as e:
            print(e)
            await ctx.send(f"{emotes.red_mark} Something failed while trying to unban.")
    
    @commands.command(brief="Unban all members", description="Unban everyone from the server.")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True, use_external_emojis=True, manage_messages=True)
    async def unbanall(self, ctx, *, reason: str=None):
        """ Unban all users from the server """
        bans = len(await ctx.guild.bans())

        try:
            unbanned = 0
            
            if bans == 0:
                return await ctx.send("This guild has no bans.")
            
            def check(r, u):
                return u.id == ctx.author.id and r.message.id == checkmsg.id
                
            checkmsg = await ctx.send(f"Are you sure you want to unban **{bans}** members from this guild?")
            await checkmsg.add_reaction(f'{emotes.white_mark}')
            await checkmsg.add_reaction(f'{emotes.red_mark}')
            await checkmsg.add_reaction('🔍')
            react, user = await self.bot.wait_for('reaction_add', check=check, timeout=30.0)

            # ? They want to unban everyone

            if str(react) == f"{emotes.white_mark}": 
                unb = await ctx.channel.send(f"Unbanning **{bans}** members from this guild.")    
                await checkmsg.delete()
                for user in await ctx.guild.bans():
                    await ctx.guild.unban(user.user, reason=responsible(ctx.author, reason))
                    await unb.edit(content=f"{emotes.loading1} Processing unbans...")
                await unb.edit(content=f"Unbanned **{bans}** members from this guild.", delete_after=15)

            # ? They don't want to unban anyone

            if str(react) == f"{emotes.red_mark}":      
                await checkmsg.delete()
                await ctx.channel.send("Alright. Not unbanning anyone..")

            # ? They want to see ban list

            if str(react) == "🔍":
                await checkmsg.clear_reactions()
                ban = []
                for banz in await ctx.guild.bans():
                    ben = f"• {banz.user}\n"
                    ban.append(ben)
                    e = discord.Embed(color=self.bot.embed_color, title=f"Bans for {ctx.guild}", description="".join(ban))
                    e.set_footer(text="Are you sure you want to unban them all?")
                    await checkmsg.edit(content='', embed=e)
                await checkmsg.add_reaction(f'{emotes.white_mark}')
                await checkmsg.add_reaction(f'{emotes.red_mark}')
                react, user = await self.bot.wait_for('reaction_add', check=check, timeout=30.0)

                # ? They want to unban everyone
                

                if str(react) == f"{emotes.white_mark}": 
                    unb = await ctx.channel.send(f"Unbanning **{bans}** members from this guild.")    
                    await checkmsg.delete()
                    for user in await ctx.guild.bans():
                        await ctx.guild.unban(user.user, reason=responsible(ctx.author, reason))
                        await unb.edit(content=f"{emotes.loading1} Processing unbans...")
                    await unb.edit(content=f"Unbanned **{bans}** members from this guild.", delete_after=15)

                # ? They don't want to unban anyone

                if str(react) == f"{emotes.red_mark}":      
                    await checkmsg.delete()
                    await ctx.channel.send("Alright. Not unbanning anyone..")

        except Exception as e:
            print(e)
            return

                

    @commands.command(brief="Softban members", description="Softbans member from the server")
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True, manage_messages=True)
    async def softban(self, ctx, user: discord.Member, reason: str = None):
        """ Softbans member from the server """


        try:
            member = user
            if user == ctx.author:
                return await ctx.send("Are you seriously trying to ban yourself? That's stupid")
            elif user.top_role.position >= ctx.author.top_role.position:
                return await ctx.send("You can't ban user who's above or equal to you!")
            elif member.top_role.position >= ctx.guild.me.top_role.position:
                return await ctx.send(f"I was unable to soft-ban {user.name}")
            obj = discord.Object(id=user.id)
            await ctx.guild.ban(obj, reason=responsible(ctx.author, reason))
            await ctx.guild.unban(obj, reason=responsible(ctx.author, reason))
            await ctx.send(f"{emotes.white_mark} **{user}** was soft-banned successfully, with a reason: ``{reason}``", delete_after=15)
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to soft-ban **{user}**.")
    
    @commands.command(brief="Mute someone")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def mute(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = None):
        """ Mute someone in your server. 
        Make sure you have muted role in your server and properly configured."""
        message = []

        muterole = discord.utils.find(lambda r: r.name.lower() == "muted", ctx.guild.roles)

        if muterole is None:
            embed = discord.Embed(color=self.bot.embed_color, description=f"{emotes.red_mark} I can't find a role named `Muted` Are you sure you've made one?")
            return await ctx.send(embed=embed, delete_after=10)

        if muterole.position > ctx.guild.me.top_role.position:
            return await ctx.send(f"{emotes.warning} Mute role is higher than me and I cannot access it.")


        try:
            total = len(members)

            if total == 0:
                return await ctx.send("Please provide members to mute.")

            if total > 10:
                return await ctx.send("You can mute only 10 members at once!")                    
            

            failed = 0
            failed_list = ""
            for member in members:
                if muterole in member.roles:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.author.top_role.position:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.guild.me.top_role.position:
                    failed += 1
                    continue
                if member == ctx.author:
                    failed += 1
                    continue
                try:
                    await member.add_roles(muterole, reason=responsible(ctx.author, reason))
                    await self.log_mute(ctx, member=member, reason=reason)
                    await self.bot.db.execute("INSERT INTO moddata(guild_id, user_id, mod_id, reason, time, role_id) VALUES($1, $2, $3, $4, $5, $6)", ctx.guild.id, member.id, ctx.author.id, responsible(ctx.author, reason), None, muterole.id)
                except discord.HTTPException as e:
                    print(e)
                    failed += 1
                    failed_list += f"{member.mention} - {e}"
                except discord.Forbidden as e:
                    print(e)
                    failed += 1
                    failed_list += f"{member.mention} - {e}"

            if failed == 0:
                await ctx.send(f"{emotes.white_mark} Succesfully muted **{total}** members for: `{reason}`.")
            elif failed != 0 and total - failed != 0:
                await ctx.send(f"Successfully muted **{total - failed}/{total}** members for: `{reason}`.")
            elif failed != 0 and total - failed == 0:
                await ctx.send(f"{emotes.red_mark} Failed to mute all the members")
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to mute members.")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def tempmute(self, ctx, duration: str, members: commands.Greedy[discord.Member], *, reason: str = None):
        """ Temporarily mutes a member 
        Use these duration examples for it to properly work:
        `1d` - 1 day
        `1h` - 1 hour
        `1m` - 1 minute
        `1s` - 1 second
        Make sure you have muted role in your server and properly configured"""

        muterole = discord.utils.find(lambda r: r.name.lower() == "muted", ctx.guild.roles)

        if muterole is None:
            embed = discord.Embed(color=self.bot.embed_color, description=f"{emotes.red_mark} I can't find a role named `Muted` Are you sure you've made one?")
            return await ctx.send(embed=embed, delete_after=10)

        if muterole.position > ctx.guild.me.top_role.position:
            return await ctx.send(f"{emotes.warning} Mute role is higher than me and I cannot access it.")

        if not duration[:-1].isdigit():
            return await ctx.send(f"{emotes.warning} Invalid time format provided!")

        if 'd' in duration.lower():
            dur = int(duration[:-1]) * 60 * 60 * 24
            if int(duration[:-1]) == 1:
                tm = 'day'
            elif int(duration[:-1]) > 1:
                tm = 'days'
        elif 'h' in duration.lower():
            dur = int(duration[:-1]) * 60 * 60
            if int(duration[:-1]) == 1:
                tm = 'hour'
            elif int(duration[:-1]) > 1:
                tm = 'hours'
        elif 'm' in duration.lower():
            dur = int(duration[:-1]) * 60
            if int(duration[:-1]) == 1:
                tm = 'minute'
            elif int(duration[:-1]) > 1:
                tm = 'minutes'
        elif 's' in duration.lower():
            dur = int(duration[:-1])
            if int(duration[:-1]) == 1:
                tm = 'second'
            elif int(duration[:-1]) > 1:
                tm = 'seconds'
        else:
            dur = 10 * 60
            tm = 'minutes'
        durations = time.time() + dur

        try:
            total = len(members)

            if total == 0:
                return await ctx.send("Please provide members to mute.")

            if total > 10:
                return await ctx.send("You can mute only 10 members at once!")                    
            

            failed = 0
            # failed_list = ""
            for member in members:
                if muterole in member.roles:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.author.top_role.position:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.guild.me.top_role.position:
                    failed += 1
                    continue
                if member == ctx.author:
                    failed += 1
                    continue
                try:
                    await member.add_roles(muterole, reason=responsible(ctx.author, reason))
                    tmd = f"{duration[:-1]} {tm}"
                    await self.log_mute(ctx, member=member, reason=reason, timed=tmd)
                    await self.bot.temp_punishment(ctx.guild.id, member.id, ctx.author.id, reason, durations, muterole.id)
                except discord.HTTPException as e:
                    print(e)
                    failed += 1
                    # failed_list += f"{member.mention} - {e}"
                except discord.Forbidden as e:
                    print(e)
                    failed += 1
                    # failed_list += f"{member.mention} - {e}"

            if failed == 0:
                await ctx.send(f"{emotes.white_mark} Succesfully muted **{total}** members for: `{reason}` (`{duration[:-1]}` {tm}).")
            elif failed != 0 and total - failed != 0:
                await ctx.send(f"{emotes.warning} Successfully muted **{total - failed}/{total}** members for: `{reason}` (`{duration[:-1]}` {tm}).")
            elif failed != 0 and total - failed == 0:
                await ctx.send(f"{emotes.red_mark} Failed to mute all the members")
        except Exception as e:
            print(e)
            await ctx.send(f"{emotes.error} Something failed while trying to mute members.")
        

    @commands.command(brief="Unmute someone", description="Unmute someone from this server")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx, members: commands.Greedy[discord.Member], *, reason: str = None):
        """ Unmute someone in the server. 
        Make sure bot has permissions to deassign the `Muted` role."""
        
        muterole = discord.utils.find(lambda r: r.name.lower() == "muted", ctx.guild.roles)

        if muterole is None:
            embed = discord.Embed(color=self.bot.embed_color, description=f"{emotes.red_mark} I can't find a role named `Muted` Are you sure you've made one?")
            return await ctx.send(embed=embed, delete_after=10)

        if muterole.position > ctx.guild.me.top_role.position:
            return await ctx.send(f"{emotes.warning} Mute role is higher than me and I cannot access it.")

        try:
            total = len(members)

            if total == 0:
                return await ctx.send("Please provide members to mute.")            

            failed = 0
            failed_list = ""
            for member in members:
                if muterole not in member.roles:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.author.top_role.position:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.guild.me.top_role.position:
                    failed += 1
                    continue
                if member == ctx.author:
                    failed += 1
                    continue
                try:
                    await member.remove_roles(muterole, reason=responsible(ctx.author, reason))
                    await self.log_unmute(ctx, member=member, reason=reason)
                    await self.bot.db.execute("DELETE FROM moddata WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id)
                    for g, u, m, r, t, ro in self.bot.temp_timer:
                        self.bot.temp_timer.remove((g, u, m, r, t, ro))
                except discord.HTTPException as e:
                    failed += 1
                    failed_list += f"{member.mention} - {e}"
                except discord.Forbidden as e:
                    failed += 1
                    failed_list += f"{member.mention} - {e}"

            if failed == 0:
                await ctx.send(f"{emotes.white_mark} Succesfully unmuted **{total}** members for: `{reason}`.")
            elif failed != 0 and total - failed != 0:
                await ctx.send(f"Successfully unmuted **{total - failed}/{total}** members for: `{reason}`.")
            elif failed != 0 and total - failed == 0:
                await ctx.send(f"{emotes.red_mark} Failed to mute all the members")
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to unmute members.")
            
    @commands.command(brief="Dehoist members", description="Dehoist all members to specific nickname")
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def dehoist(self, ctx, *, nick: str):
        """ Dehoist members with non alphabetic letters """        
        nickname_only = False
        try:
            hoisters = []
            changed = 0
            failed = 0
            error = ""
            await ctx.send(f'{emotes.loading2} Started dehoisting process...')
            for hoister in ctx.guild.members:
                if nickname_only:
                    if not hoister.nick: return
                    name = hoister.nick
                else:
                    name = hoister.display_name
                if not name[0].isalnum():
                    try:
                        await hoister.edit(nick=nick, reason=responsible(ctx.author, 'member was dehoisted.'))
                        changed += 1
                        hoisters.append(f"{hoister.mention} ({hoister.id}) - {hoister} ")
                    except Exception as e:
                        failed += 1
                        error += f"• {hoister.mention} ({hoister.id}) - {e}\n"
                        pass
            if not hoisters and failed == 0:
                return await ctx.send(f"{emotes.warning} | No hoisters were found.")
            
            if changed == 0 and failed != 0:
                msg = f"\n\n**I failed to dehoist {failed} member(s):**\n{error}"
                return await ctx.send(msg[:1980])
            
            if len(hoisters) > 20:
                hoisters = hoisters[:20]
            msg = f"**Following member(s) were dehoisted: `(Total: {changed})`**"
            for num, hoist in enumerate(hoisters, start=0):
                msg += f"\n`[{num+1}]` {hoist}"
            
            if changed > 20:
                msg += "\nSorry, that caps out at 20."

            if failed != 0:
                msg += f"\n\n**However I failed to dehoist {failed} member(s):**\n{error}"
            
            if len(msg) >= 1980:
                msg = msg[:1980]
                msg += "... Limit :("
            await ctx.send(msg)
                        
        except Exception as e:
            return await ctx.send(e)
    
    @commands.command(brief="Clone text channel", description="Clone text channel in this server")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def clone(self, ctx, channel: discord.TextChannel, *, reason: str = None):
        """ Clone text channel in the server"""
        server = ctx.message.guild
        if reason is None:
            reason = 'No reason'
        try:
            await ctx.message.delete()
        except:
            pass
        for c in ctx.guild.channels:
            if c.name == f'{channel.name}-clone':
                return await ctx.send(f"{emotes.red_mark} {channel.name} clone already exists!")     
        await channel.clone(name=f'{channel.name}-clone', reason=responsible(ctx.author, reason))
        await ctx.send(f"{emotes.white_mark} Successfully cloned {channel.name}")

    @commands.group(aliases=['clear', 'delete', 'prune'], brief="Clear messages", description="Clear messages from the chat", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx):
        """ Purge messages in the chat. Default amount is set to **100**"""
        await ctx.send_help(ctx.command)   
    @purge.command(brief="Every message", description="Clear all messages in chat")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def all(self, ctx, search=100):
        """ Removes all messages
        Might take longer if you're purging messages that are older than 2 weeks """
        await ctx.message.delete()
        await self.do_removal(ctx, search, lambda e: True)
    
    @purge.command(brief="User messages", description="Clear messages sent from an user")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def user(self, ctx, member: discord.Member, search=100):
        """ Removes user messages """
        await ctx.message.delete()
        await self.do_removal(ctx, search, lambda e: e.author == member)
    
    @purge.command(brief="Bot's messages", description="Clear messages sent from an user")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    @commands.guild_only()
    async def bot(self, ctx, bot: discord.Member, search=100):
        """ Removes bot's messages """
        if not bot.bot:
            return await ctx.send(f'{emotes.red_mark} Please define a valid bot.')
        await ctx.message.delete()
        await self.do_removal(ctx, search, lambda e: e.author == bot)
    
    @commands.command(brief="Voice mute member", description="Voice mute any member in the server", aliases=["vmute"])
    @commands.guild_only()
    @commands.has_guild_permissions(mute_members=True)
    @commands.bot_has_guild_permissions(mute_members=True)
    async def voicemute(self, ctx, members: commands.Greedy[discord.Member], reason: str=None):
        """ Voice mute member in the server """

        try:
            total = len(members)

            if total == 0:
                return await ctx.send("Please provide members to voice mute.")

            if total > 5:
                return await ctx.send("You can voicemute only 5 members at once.")            

            failed = 0
            for member in members:
                if member.top_role.position >= ctx.author.top_role.position:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.guild.me.top_role.position:
                    failed += 1
                    continue
                if member == ctx.author:
                    failed += 1
                    continue
                try:
                    await member.edit(mute=True, reason=responsible(ctx.author, reason))
                except discord.HTTPException as e:
                    failed += 1
                except discord.Forbidden:
                    failed += 1

            if failed == 0:
                await ctx.send(f"{emotes.white_mark} Succesfully voice muted **{total}** members.")
            else:
                await ctx.send(f"Successfully voice muted **{total - failed}/{total}** members.")
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to voice mute members.")


    @commands.command(brief="Voice unmute member", description="Voice unmute any member in the server", aliases=["vunmute"])
    @commands.guild_only()
    @commands.has_guild_permissions(mute_members=True)
    @commands.bot_has_guild_permissions(mute_members=True)
    async def voiceunmute(self, ctx, members: commands.Greedy[discord.Member], reason: str=None):
        """ Voice unmute member in the server """

        try:
            total = len(members)

            if total == 0:
                return await ctx.send("Please provide members to voice unmute.")

            if total > 5:
                return await ctx.send("You can voice unmute only 5 members at once.")            

            failed = 0
            for member in members:
                if member.top_role.position >= ctx.author.top_role.position:
                    failed += 1
                    continue
                if member.top_role.position >= ctx.guild.me.top_role.position:
                    failed += 1
                    continue
                if member == ctx.author:
                    failed += 1
                    continue
                try:
                    await member.edit(mute=False, reason=responsible(ctx.author, reason))
                except discord.HTTPException:
                    failed += 1

            if failed == 0:
                await ctx.send(f"{emotes.white_mark} Succesfully voice unmuted **{total}** members.")
            else:
                await ctx.send(f"Successfully voice unmuted **{total - failed}/{total}** members.")
        except Exception as e:
            print(e)
            await ctx.send(f"Something failed while trying to voice unmute members.")
    
    @commands.command(brief="New users", hidden=True)
    @commands.guild_only()
    async def newusers(self, ctx, *, count: int):
        """
        See the newest members in the server.
        Limit is set to `10`
        """
        if len(ctx.guild.members) < count:
            return await ctx.send(f"This server has only {len(ctx.guild.members)} members")
        counts = max(min(count, 10), 1)

        if not ctx.guild.chunked:
            await self.bot.request_offline_members(ctx.guild)
        members = sorted(ctx.guild.members, key=lambda m: m.joined_at, reverse=True)[:counts]
        e = discord.Embed(title='Newest member(s) in this server', colour=self.bot.embed_color)
        for member in members:
            data = f'**Joined Server at** {btime.human_timedelta(member.joined_at)}\n**Account created at** {btime.human_timedelta(member.created_at)}'
            e.add_field(name=f'**{member}** ({member.id})', value=data, inline=False)
            if count > 10:
                e.set_footer(text="Limit is set to 10")

        await ctx.send(embed=e)

    @commands.command(brief="Hoist a role", aliases=['ar'])
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def announcerole(self, ctx, *, role: discord.Role):
        """ Make a role mentionable you want to mention in announcements.
        
        The role will become unmentionable after you mention it or you don't mention it for 30seconds. """
        if role == ctx.guild.default_role:
            return await ctx.send("To prevent abuse, I won't allow mentionable role for everyone/here role.")

        if ctx.author.top_role.position <= role.position:
            return await ctx.send("It seems like the role you attempt to mention is over your permissions, therefor I won't allow you.")

        if ctx.me.top_role.position <= role.position:
            return await ctx.send("This role is above my permissions, I can't make it mentionable ;-;")

        if role.mentionable == True:
            return await ctx.send(f"{emotes.red_mark} That role is already mentionable!")

        await role.edit(mentionable=True, reason=f"announcerole command")
        msg = await ctx.send(f"**{role.mention}** is now mentionable, if you don't mention it within 30 seconds, I will revert the changes.")

        while True:
            def role_checker(m):
                if (role.mention in m.content):
                    return True
                return False

            try:
                checker = await self.bot.wait_for('message', timeout=30.0, check=role_checker)
                if checker.author.id == ctx.author.id:
                    await role.edit(mentionable=False, reason=f"announcerole command")
                    return await msg.edit(content=f"**{role.mention}** mentioned by **{ctx.author}** in {checker.channel.mention}", allowed_mentions=discord.AllowedMentions(roles=False))
                    break
                else:
                    await checker.delete()
            except asyncio.TimeoutError:
                await role.edit(mentionable=False, reason=f"announcerole command")
                return await msg.edit(content=f"**{role.mention}** was never mentioned by **{ctx.author}**...", allowed_mentions=discord.AllowedMentions(roles=False))
                break
    
    @commands.command(brief="Member warnings", aliases=['warns'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx, member: discord.Member = None):
        """ Check all guild warns or all member warnings """

        if member is None:
            warns_check = await self.bot.db.fetchval("SELECT * FROM warnings WHERE guild_id = $1", ctx.guild.id)
            
            if warns_check is None:
                return await ctx.send(f"There are no warnings in this guild.")
                
            if warns_check is not None:
                user = []
                for user_id, reason, id, time in await self.bot.db.fetch("SELECT user_id, reason, id, time FROM warnings WHERE guild_id = $1", ctx.guild.id):
                    user.append(f'**User:** {ctx.guild.get_member(user_id)}\n' + '**ID:** ' + str(id) + "\n" + '**Reason:** ' + reason + "\n**Warned:** " + str(date(time)) + "\n**────────────────────────**")
                
                members = []
                for reason in user:
                    members.append(f"{reason}\n")
                    
                paginator = Pages(ctx,
                          title=f"Guild warnings",
                          entries=members,
                          thumbnail=None,
                          per_page = 5,
                          embed_color=ctx.bot.embed_color,
                          show_entry_count=True,
                          author=ctx.author)
                await paginator.paginate()
        

        if member is not None:
            warns_check = await self.bot.db.fetchval("SELECT * FROM warnings WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id)
            
            if warns_check is None:
                return await ctx.send(f"**{member}** has no warnings.")
                
            if warns_check is not None:
                user = []
                for reason, id, mod, time in await self.bot.db.fetch("SELECT reason, id, mod_id, time FROM warnings WHERE guild_id = $1 AND user_id = $2", ctx.guild.id, member.id):
                    mod = ctx.guild.get_member(mod)

                    if mod is not None:
                        mod = mod
                    elif mod is None:
                        mod = 'Unable to track'
                    user.append('**ID:** ' + str(id) + "\n" + '**Reason:** ' + reason + "\n**Warned:** " + str(date(time)) + "\n**Warned by:** " + str(mod) + "\n**────────────────────────**")
                
                members = []
                for reason in user:
                    members.append(f"{reason}\n")
                    
                paginator = Pages(ctx,
                          title=f"{member}'s warnings",
                          entries=members,
                          thumbnail=None,
                          per_page = 5,
                          embed_color=ctx.bot.embed_color,
                          show_entry_count=True,
                          author=ctx.author)
                await paginator.paginate()

    @commands.command(brief="Warn a member")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = None):
        """ Warn a member for something
        Time will be logged in UTC """

        if reason is None:
            reason = "No reason."
        else:
            reason = reason
        
        if member == ctx.author:
            return await ctx.send("Ok you're warned, dummy...")
        if member.top_role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
            return await ctx.send("You can't warn someone who's higher or equal to you!")

        random_id = random.randint(1111, 99999)
        
        await self.bot.db.execute("INSERT INTO warnings(user_id, guild_id, id, reason, time, mod_id) VALUES ($1, $2, $3, $4, $5, $6)", member.id, ctx.guild.id, random_id, reason, datetime.utcnow(), ctx.author.id)

        e = discord.Embed(color=self.bot.embed_color, description=f"Successfully warned **{member}** for: **{reason}** with ID: **{random_id}**", delete_after=15)

        await ctx.send(embed=e)

    @commands.command(brief="Remove warn from member", aliases=['unwarn'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def removewarn(self, ctx, member: discord.Member, warnid):
        """ Remove warn from member's history """

        if member is ctx.author:
            return await ctx.send("Ok your warn was removed, dummy...")
        if member.top_role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
            return await ctx.send("You can't remove warns from someone who's higher or equal to you!")

        check_id = await self.bot.db.fetchval('SELECT * FROM warnings WHERE guild_id = $1 AND id = $2', ctx.guild.id, int(warnid))

        if check_id is None:
            await ctx.send(f"Warn with ID: **{warnid}** was not found.")

        if check_id is not None:
            warnings = await self.bot.db.fetchval('SELECT * FROM warnings WHERE user_id = $1 AND id = $2', member.id, int(warnid))
            if warnings is not None:
                await self.bot.db.execute("DELETE FROM warnings WHERE id = $1 AND user_id = $2", int(warnid), member.id)
                await ctx.send(f"Removed warn from **{member}** with id: **{int(warnid)}**")
            if warnings is None:
                return await ctx.send(f"Warn with ID: **{int(warnid)}** was not found.")
    
    @commands.command(brief="Remove all warns from member", aliases=['unwarnall'])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(use_external_emojis=True)
    async def removewarns(self, ctx, member: discord.Member):
        """ Remove all member's warns """

        try:
            if member is ctx.author:
                return await ctx.send("Ok your warns were removed, dummy...")
            if member.top_role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
                return await ctx.send("You can't remove warns from someone who's higher or equal to you!")

            def check(r, u):
                return u.id == ctx.author.id and r.message.id == checkmsg.id
            sel = await self.bot.db.fetch("SELECT * FROM warnings WHERE user_id = $1 AND guild_id = $2", member.id, ctx.guild.id)

            if len(sel) == 0:
                return await ctx.send(f"**{member}** has no warnings.")
            checkmsg = await ctx.send(f"Are you sure you want to remove all **{len(sel)}** warns from the **{member}**?")
            await checkmsg.add_reaction(f'{emotes.white_mark}')
            await checkmsg.add_reaction(f'{emotes.red_mark}')
            react, user = await self.bot.wait_for('reaction_add', check=check, timeout=30)

            if str(react) == f"{emotes.white_mark}":
                await checkmsg.delete()
                await self.bot.db.execute("DELETE FROM warnings WHERE user_id = $1 AND guild_id = $2", member.id, ctx.guild.id)
                await ctx.send(f"Removed **{len(sel)}** warnings from: **{member}**", delete_after=15)
            
            if str(react) == f"{emotes.red_mark}":
                await checkmsg.delete()
                return await ctx.send("Not removing any warns.", delete_after=15)

        except asyncio.TimeoutError:
            await checkmsg.clear_reactions()
            return await checkmsg.edit(content=f"Timing out...", delete_after=15)
        except Exception as e:
            print(e)
            await ctx.send("Looks like something wrong happened.")

    @commands.command(brief='Lock a text channel')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 300, commands.BucketType.guild)
    async def lockchannel(self, ctx, channel: discord.TextChannel, *, reason: str = None):
        """ Lock any text channels from everyone being able to chat """
        
        if reason is None:
            reason = "No reason"

        if channel.overwrites_for(ctx.guild.default_role).send_messages == False:
            return await ctx.send(f"{emotes.red_mark} {channel.mention} is already locked!", delete_after=20)
        else:
            await channel.set_permissions(ctx.guild.default_role, send_messages=False, reason=responsible(ctx.author, reason))
            await channel.send(f"{emotes.locked} This channel was locked for: `{reason}`")
            await ctx.send(f"{emotes.white_mark} {channel.mention} was locked!", delete_after=20)
    
    @commands.command(brief='Unlock a text channel')
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.cooldown(1, 300, commands.BucketType.guild)
    async def unlockchannel(self, ctx, channel: discord.TextChannel, *, reason: str = None):
        """ Unlock text channel to everyone 
        This will sync permissions with category """

        if reason is None:
            reason = "No reason"

        if channel.overwrites_for(ctx.guild.default_role).send_messages is None:
            return await ctx.send(f"{emotes.red_mark} {channel.mention} is not locked!", delete_after=20)
        elif channel.overwrites_for(ctx.guild.default_role).send_messages == False:
            await channel.set_permissions(ctx.guild.default_role, overwrite=None, reason=responsible(ctx.author, reason))
            await channel.send(f"{emotes.unlocked} This channel was unlocked for: `{reason}`")
            await ctx.send(f"{emotes.white_mark} {channel.mention} was unlocked!", delete_after=20)

    @commands.command(brief='Lockdown the server', hidden=True)
    @commands.guild_only()
    @commands.is_owner()
    @commands.cooldown(1, 300, commands.BucketType.guild)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def lockdown(self, ctx, *, reason: commands.clean_content):
        """ Will lock all the channels in the server """

        lock = 0
        for channel in ctx.guild.channels:
            if channel.overwrites_for(ctx.guild.default_role).read_messages == False:
                await self.bot.db.execute("INSERT INTO lockdown(guild_id, channel_id) values ($1, $2)", ctx.guild.id, channel.id)
                continue
            if channel.overwrites_for(ctx.guild.default_role).send_messages == False:
                if not await self.bot.db.fetchval("SELECT * FROM lockdown WHERE channel_id = $1 AND guild_id = $2", channel.id, ctx.guild.id):
                    await self.bot.db.execute("INSERT INTO lockdown(guild_id, channel_id) values ($1, $2)", ctx.guild.id, channel.id)
                continue
            if isinstance(channel, discord.CategoryChannel):
                continue
            try:
                await channel.set_permissions(ctx.guild.me, send_messages=True, reason=responsible(ctx.author, reason))
                await channel.set_permissions(ctx.guild.default_role, send_messages=False, connect=False, reason=responsible(ctx.author, reason))
                if isinstance(channel, discord.TextChannel):
                    await channel.send(f"{emotes.locked} **Channel locked for:** {reason}")
                lock += 1
            except Exception as e:
                print(e)
                pass
        
        await ctx.send(f"{emotes.white_mark} Locked {lock} channels")
    
    @commands.command(brief='Unlockdown the server', hidden=True)
    @commands.guild_only()
    @commands.is_owner()
    @commands.cooldown(1, 300, commands.BucketType.guild)
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unlockdown(self, ctx, *, reason: commands.clean_content):
        """ Unlock all the channels that were previously locked using a lockdown. """

        check = await self.bot.db.fetchval("SELECT * FROM lockdown WHERE guild_id = $1", ctx.guild.id)
        if check is None:
            try:
                def check(r, u):
                    return u.id == ctx.author.id and r.message.id == checkmsg.id

                channels = 0
                for channel in ctx.guild.channels:
                    if isinstance(channel, discord.CategoryChannel):
                        continue
                    channels += 1
                
                checkmsg = await ctx.send(f"No results of previously locked channels using `lockdown` were found are you sure you want to unlock all **{channels}** channels in this server?")
                await checkmsg.add_reaction(f'{emotes.white_mark}')
                await checkmsg.add_reaction(f'{emotes.red_mark}')
                react, user = await self.bot.wait_for('reaction_add', check=check, timeout=30.0)

                if str(react) == f"{emotes.white_mark}":
                    await checkmsg.edit(content=f"{emotes.loading1} Started unlocking process")
                    unlocked = 0
                    for channel in ctx.guild.channels:
                        if isinstance(channel, discord.CategoryChannel):
                            continue
                        try:
                            await channel.set_permissions(ctx.guild.default_role, overwrite=None, reason=responsible(ctx.author, reason))
                            await channel.send(f"{emotes.unlocked} **Channel unlocked for:** {reason}")
                            unlocked += 1
                        except Exception as e:
                            print(e)
                            pass
                    return await ctx.send(f"{emotes.white_mark} Unlocked {unlocked} channels.", delete_after=15)

                elif str(react) == f"{emotes.red_mark}":
                    await checkmsg.edit(content=f"Ok. Not unlocking any channels", delete_after=15)
                    try:
                        return await checkmsg.clear_reactions()
                    except:
                        return
            except asyncio.TimeoutError:
                await checkmsg.edit(content=f"{emotes.warning} Timeout!")
                try:
                    return await checkmsg.clear_reactions()
                except:
                    return

        unlocked = 0
        for channel in ctx.guild.channels:
            if channel.overwrites_for(ctx.guild.default_role).read_messages == False:
                continue      
            if await self.bot.db.fetchval("SELECT channel_id FROM lockdown WHERE guild_id = $1 and channel_id = $2", ctx.guild.id, channel.id):
                continue
            if isinstance(channel, discord.CategoryChannel):
                continue
            try:
                await channel.set_permissions(ctx.guild.default_role, read_messages = True, send_messages=True, connect=True, reason=responsible(ctx.author, reason))
                if isinstance(channel, discord.TextChannel):
                    await channel.send(f"{emotes.unlocked} **Channel unlocked for:** {reason}")
                unlocked += 1
            except Exception as e:
                print(e)
                pass

        await ctx.send(f"{emotes.white_mark} Unlocked {unlocked} channels")
        await self.bot.db.execute("DELETE FROM lockdown WHERE guild_id = $1", ctx.guild.id)
        
            
    
def setup(bot):
    bot.add_cog(moderation(bot))
