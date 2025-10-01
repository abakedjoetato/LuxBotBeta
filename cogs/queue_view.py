class SubmissionSelect(discord.ui.Select):
    """Dropdown menu to select a submission for removal."""
    def __init__(self, submissions: List[Dict[str, Any]]):
        options = []
        if not submissions:
            options.append(discord.SelectOption(label="No submissions on this page.", value="placeholder", default=True))
        else:
            for sub in submissions:
                label = f"#{sub['id']}: {sub['artist_name']} - {sub['song_name']}"
                if len(label) > 100:
                    label = label[:97] + "..."
                options.append(discord.SelectOption(label=label, value=str(sub['id'])))

        super().__init__(
            placeholder="Select a submission to remove...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=not submissions,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view: 'PaginatedQueueView' = self.view
        if not view:
            return

        view.selected_submission_id = self.values[0]
        if view.remove_button:
            view.remove_button.disabled = False
        await interaction.response.edit_message(view=view)


class PaginatedQueueView(discord.ui.View):
    """Discord View for paginated queue display with navigation and removal functionality."""
    
    def __init__(self, bot, queue_line: str, entries_per_page: int = 10):
        super().__init__(timeout=900)
        self.bot = bot
        self.queue_line = queue_line
        self.entries_per_page = entries_per_page
        self.current_page = 1
        self.total_pages = 1
        self.submissions = []
        self.message: Optional[discord.Message] = None
        self.selected_submission_id: Optional[str] = None
        self.remove_button: Optional[discord.ui.Button] = None

        self._add_navigation_buttons()
        if self.queue_line != QueueLine.CALLS_PLAYED.value:
            self._add_removal_components()

    def _add_navigation_buttons(self):
        self.previous_button = discord.ui.Button(label="◀️ Previous", style=discord.ButtonStyle.secondary, row=0)
        self.next_button = discord.ui.Button(label="Next ▶️", style=discord.ButtonStyle.secondary, row=0)
        self.go_to_page_button = discord.ui.Button(label="Go to", style=discord.ButtonStyle.primary, emoji="🔢", row=0)
        self.refresh_button = discord.ui.Button(label="Refresh", style=discord.ButtonStyle.success, emoji="🔄", row=0)

        self.previous_button.callback = self.previous_button_callback
        self.next_button.callback = self.next_button_callback
        self.go_to_page_button.callback = self.go_to_page_button_callback
        self.refresh_button.callback = self.refresh_button_callback

        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.go_to_page_button)
        self.add_item(self.refresh_button)

    def _add_removal_components(self):
        self.submission_select = SubmissionSelect([])
        self.add_item(self.submission_select)
        self.remove_button = discord.ui.Button(label="Remove Selected", style=discord.ButtonStyle.danger, emoji="🗑️", disabled=True, row=2)
        self.remove_button.callback = self.remove_button_callback
        self.add_item(self.remove_button)

    async def update_data(self):
        self.submissions = await self.bot.db.get_queue_submissions(self.queue_line)
        self.total_pages = max(1, math.ceil(len(self.submissions) / self.entries_per_page))
        if self.current_page > self.total_pages: self.current_page = self.total_pages
        elif self.current_page < 1: self.current_page = 1
        self._update_components_state()

    def _update_components_state(self):
        self.previous_button.disabled = self.current_page <= 1
        self.next_button.disabled = self.current_page >= self.total_pages
        self.go_to_page_button.disabled = self.total_pages <= 1
        if hasattr(self, 'submission_select') and self.remove_button:
            page_submissions = self.get_page_submissions()
            self.submission_select.options = SubmissionSelect(page_submissions).options
            self.submission_select.disabled = not page_submissions
            self.remove_button.disabled = True

    def get_page_submissions(self) -> List[Dict[str, Any]]:
        start_idx = (self.current_page - 1) * self.entries_per_page
        return self.submissions[start_idx:start_idx + self.entries_per_page]

    def create_embed(self, is_expired: bool = False) -> discord.Embed:
        color = self._get_line_color() if not is_expired else discord.Color.light_grey()
        embed = discord.Embed(title=f"🎵 {self.queue_line} Queue Line", color=color)
        page_submissions = self.get_page_submissions()

        if not self.submissions:
            embed.description = "This queue is currently empty."
        else:
            lines = []
            start_num = (self.current_page - 1) * self.entries_per_page + 1
            for i, sub in enumerate(page_submissions, start_num):
                link = f" ([Link]({sub['link_or_file']}))" if sub['link_or_file'].startswith('http') else " (File)"
                is_played = self.queue_line == QueueLine.CALLS_PLAYED.value
                time_val = sub.get('played_time') if is_played else sub.get('submission_time')
                time_prefix = "Played" if is_played else "Submitted"
                ts_str = ""
                if time_val:
                    try:
                        ts = datetime.datetime.fromisoformat(time_val)
                        ts_str = f" ({time_prefix} <t:{int(ts.timestamp())}:R>)"
                    except (ValueError, TypeError): pass
                lines.append(f"**{i}.** `#{sub['id']}`: **{sub['artist_name']} – {sub['song_name']}** by *{sub['username']}*{ts_str}{link}")
            embed.description = "\n".join(lines)

        footer = f"Total submissions: {len(self.submissions)}"
        if self.total_pages > 1: footer = f"Page {self.current_page} of {self.total_pages} | {footer}"
        if is_expired:
            embed.description = "This interactive view has expired."
            footer = "View has expired"
        embed.set_footer(text=f"{footer} | Luxurious Radio By Emerald Beats")
        embed.timestamp = discord.utils.utcnow()
        return embed

    def _get_line_color(self) -> discord.Color:
        colors = {q.value: c for q, c in zip(QueueLine, [discord.Color.red(), discord.Color.orange(), discord.Color.yellow(), discord.Color.green(), discord.Color.purple()])}
        return colors.get(self.queue_line, discord.Color.default())

    async def _update_view_from_interaction(self, interaction: discord.Interaction):
        await self.update_data()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def previous_button_callback(self, interaction: discord.Interaction):
        if self.current_page > 1:
            self.current_page -= 1
            await self._update_view_from_interaction(interaction)
        else: await interaction.response.defer()

    async def next_button_callback(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self._update_view_from_interaction(interaction)
        else: await interaction.response.defer()

    async def go_to_page_button_callback(self, interaction: discord.Interaction):
        if self.total_pages <= 1:
            await interaction.response.defer()
            return
        await interaction.response.send_modal(GoToPageModal(self))

    async def refresh_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.update_data()
        await interaction.edit_original_response(embed=self.create_embed(), view=self)

    async def remove_button_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ You do not have permission to remove submissions.", ephemeral=True)
            return
        if not self.selected_submission_id or self.selected_submission_id == "placeholder":
            await interaction.response.send_message("⚠️ No submission selected.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        sub_id = int(self.selected_submission_id)
        original_line = await self.bot.db.remove_submission(sub_id)

        if original_line:
            await interaction.followup.send(f"✅ Submission #{sub_id} has been removed.", ephemeral=True)
            await self.update_data()
            if self.message:
                await self.message.edit(embed=self.create_embed(), view=self)
        else:
            await interaction.followup.send(f"❌ Could not find or remove submission #{sub_id}.", ephemeral=True)
        self.selected_submission_id = None

    async def on_timeout(self):
        for item in self.children: item.disabled = True
        if self.message:
            try:
                await self.message.edit(embed=self.create_embed(is_expired=True), view=self)
            except discord.HTTPException: pass

class GoToPageModal(discord.ui.Modal, title="Go to Page"):
    """Modal for jumping to a specific page."""
    
    page_number = discord.ui.TextInput(label='Page Number', placeholder='Enter page number...', required=True, max_length=5)
    
    def __init__(self, queue_view: PaginatedQueueView):
        super().__init__()
        self.queue_view = queue_view
        self.page_number.label = f'Page Number (1-{queue_view.total_pages})'
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_page = int(self.page_number.value)
            if 1 <= target_page <= self.queue_view.total_pages:
                self.queue_view.current_page = target_page
                await self.queue_view._update_view_from_interaction(interaction)
            else:
                await interaction.response.send_message(f"❌ Invalid page. Enter a number between 1 and {self.queue_view.total_pages}.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number.", ephemeral=True)


class QueueViewCog(commands.Cog):
    """Cog for managing paginated queue views"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def create_or_update_queue_view(self, queue_line: str):
        """Create or update a paginated queue view in its designated channel."""
        channel_settings = await self.bot.db.get_channel_for_line(queue_line)
        if not (channel_settings and channel_settings['channel_id']):
            return
            
        channel = self.bot.get_channel(channel_settings['channel_id'])
        if not channel:
            return

        entries_per_page = 25 if queue_line == QueueLine.CALLS_PLAYED.value else 10
        view = PaginatedQueueView(self.bot, queue_line, entries_per_page=entries_per_page)
        await view.update_data()
        embed = view.create_embed()

        try:
            if channel_settings['pinned_message_id']:
                message = await channel.fetch_message(channel_settings['pinned_message_id'])
                await message.edit(embed=embed, view=view)
                view.message = message
            else:
                await self._create_new_pinned_message(channel, embed, view, queue_line)
        except discord.NotFound:
            await self._create_new_pinned_message(channel, embed, view, queue_line)
        except discord.Forbidden:
            print(f"Missing permissions to update queue view in channel {channel.id} for line {queue_line}.")
        except discord.HTTPException as e:
            print(f"Failed to update queue view for {queue_line}: {e}")
    
    async def _create_new_pinned_message(self, channel, embed, view, queue_line):
        """Create a new pinned message for the queue view."""
        try:
            message = await channel.send(embed=embed, view=view)
            await message.pin(reason="Queue display message")
            await self.bot.db.update_pinned_message(queue_line, message.id)
            view.message = message
        except discord.Forbidden:
            print(f"Missing permissions to pin message in channel {channel.id} for line {queue_line}.")
        except discord.HTTPException as e:
            print(f"Failed to create new pinned message for {queue_line}: {e}")

async def setup(bot):
    """Setup function for the cog"""
    await bot.add_cog(QueueViewCog(bot))