from django.db import models


class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=10, help_text="e.g. TKM, MI, CSK")
    logo = models.ImageField(upload_to='team_logos/', blank=True, null=True)
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='teams_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Player(models.Model):
    ROLE_CHOICES = [
        ('batsman', 'Batsman'),
        ('bowler', 'Bowler'),
        ('allrounder', 'All-rounder'),
        ('wicketkeeper', 'Wicket-keeper'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='players')
    name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    jersey_number = models.PositiveIntegerField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='player_photos/', blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.team.short_name})"


class Match(models.Model):
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('live', 'Live'),
        ('completed', 'Completed'),
    ]

    TOSS_DECISION_CHOICES = [
        ('bat', 'Bat'),
        ('bowl', 'Bowl'),
    ]

    team_a = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='matches_as_team_a')
    team_b = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='matches_as_team_b')
    overs_limit = models.PositiveIntegerField(default=20, help_text="Total overs per innings, e.g. 20 for T20")
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_created')
    match_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')

    toss_winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='toss_wins')
    toss_decision = models.CharField(max_length=10, choices=TOSS_DECISION_CHOICES, blank=True)

    winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_won')
    result_summary = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.team_a.short_name} vs {self.team_b.short_name} - {self.match_date.strftime('%d %b %Y')}"
    def calculate_man_of_match(self):
        player_scores = {}

        for innings in self.innings.all():
            for stat in innings.batting_stats():
                p = stat['player']
                player_scores.setdefault(p.id, {'player': p, 'points': 0})
                player_scores[p.id]['points'] += stat['runs']
                player_scores[p.id]['points'] += stat['fours'] * 1
                player_scores[p.id]['points'] += stat['sixes'] * 2

            for stat in innings.bowling_stats():
                p = stat['player']
                player_scores.setdefault(p.id, {'player': p, 'points': 0})
                player_scores[p.id]['points'] += stat['wickets'] * 20

        if not player_scores:
            return None

        best = max(player_scores.values(), key=lambda x: x['points'])
        return best['player']


class Innings(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='innings')
    batting_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='innings_batted')
    bowling_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='innings_bowled')
    innings_number = models.PositiveIntegerField(help_text="1st or 2nd innings")

    current_striker = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='striking_innings')
    current_non_striker = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='non_striking_innings')
    current_bowler = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='current_bowling_innings')

    is_completed = models.BooleanField(default=False)

    def total_runs(self):
        return sum(ball.total_runs() for ball in self.balls.all())
    

    def total_wickets(self):
        return self.balls.filter(is_wicket=True).count()
    
    
    def overs_summary(self):
        """Returns [{'over_number': 1, 'cumulative_runs': 8}, ...] built from Ball data."""
        balls = self.balls.order_by('over_number', 'ball_number')
        per_over = {}
        for ball in balls:
            per_over.setdefault(ball.over_number, 0)
            per_over[ball.over_number] += ball.total_runs()

        result = []
        cumulative = 0
        for over_num in sorted(per_over.keys()):
            cumulative += per_over[over_num]
            result.append({'over_number': over_num, 'cumulative_runs': cumulative})
        return result

    def legal_balls_count(self):
        return self.balls.filter(extra_type__in=['', 'bye', 'legbye']).count()

    def overs_bowled(self):
        legal_balls = self.legal_balls_count()
        overs = legal_balls // 6
        balls = legal_balls % 6
        return f"{overs}.{balls}"

    def batting_stats(self):
        stats = {}
        for ball in self.balls.all():
            p = ball.batsman
            if p.id not in stats:
                stats[p.id] = {'player': p, 'runs': 0, 'balls': 0, 'fours': 0, 'sixes': 0, 'out': False}
            if ball.extra_type != 'wide':
                stats[p.id]['balls'] += 1
            stats[p.id]['runs'] += ball.runs
            if ball.runs == 4:
                stats[p.id]['fours'] += 1
            if ball.runs == 6:
                stats[p.id]['sixes'] += 1
            if ball.is_wicket and ball.player_out_id == p.id:
                stats[p.id]['out'] = True

        for s in stats.values():
            s['strike_rate'] = round((s['runs'] / s['balls']) * 100, 1) if s['balls'] else 0.0
        return list(stats.values())

    def bowling_stats(self):
        stats = {}
        for ball in self.balls.all():
            p = ball.bowler
            if p.id not in stats:
                stats[p.id] = {'player': p, 'balls': 0, 'runs': 0, 'wickets': 0}
            if ball.extra_type in ['', 'bye', 'legbye']:
                stats[p.id]['balls'] += 1
            if ball.extra_type not in ['bye', 'legbye']:
                stats[p.id]['runs'] += ball.total_runs()
            if ball.is_wicket and ball.wicket_type != 'runout':
                stats[p.id]['wickets'] += 1

        for s in stats.values():
            overs = s['balls'] / 6
            s['overs_display'] = f"{s['balls'] // 6}.{s['balls'] % 6}"
            s['economy'] = round(s['runs'] / overs, 2) if overs else 0.0
        return list(stats.values())

    def __str__(self):
        return f"{self.batting_team.short_name} innings ({self.match})"
    
    def current_partnership(self):
        balls = list(self.balls.order_by('id'))
        current = []
        for b in reversed(balls):
            if b.is_wicket:
                break
            current.insert(0, b)
        runs = sum(b.total_runs() for b in current)
        balls_faced = len([b for b in current if b.extra_type != 'wide'])
        return {'runs': runs, 'balls': balls_faced}

    def target_info(self):
        if self.innings_number != 2:
            return None
        first_innings = self.match.innings.filter(innings_number=1).first()
        if not first_innings:
            return None
        target = first_innings.total_runs() + 1
        runs_needed = target - self.total_runs()
        max_balls = self.match.overs_limit * 6
        balls_remaining = max_balls - self.legal_balls_count()
        if balls_remaining <= 0 or runs_needed <= 0:
            return None
        overs_remaining = balls_remaining / 6
        rrr = round(runs_needed / overs_remaining, 2)
        balls_display = f"{balls_remaining // 6}.{balls_remaining % 6}"
        return {
            'target': target,
            'runs_needed': runs_needed,
            'overs_remaining': balls_display,
            'rrr': rrr,
        }


class Ball(models.Model):
    EXTRA_CHOICES = [
        ('', 'None'),
        ('wide', 'Wide'),
        ('noball', 'No Ball'),
        ('bye', 'Bye'),
        ('legbye', 'Leg Bye'),
    ]

    WICKET_TYPE_CHOICES = [
        ('bowled', 'Bowled'),
        ('caught', 'Caught'),
        ('lbw', 'LBW'),
        ('runout', 'Run Out'),
        ('stumped', 'Stumped'),
        ('other', 'Other'),
    ]

    innings = models.ForeignKey(Innings, on_delete=models.CASCADE, related_name='balls')
    over_number = models.PositiveIntegerField()
    ball_number = models.PositiveIntegerField(help_text="1 to 6 within the over")

    batsman = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='balls_faced')
    bowler = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='balls_bowled')

    runs = models.PositiveIntegerField(default=0, help_text="Runs off the bat (not including extras)")
    extra_type = models.CharField(max_length=10, choices=EXTRA_CHOICES, blank=True)
    extra_runs = models.PositiveIntegerField(default=0)

    is_wicket = models.BooleanField(default=False)
    wicket_type = models.CharField(max_length=10, choices=WICKET_TYPE_CHOICES, blank=True)
    player_out = models.ForeignKey(Player, on_delete=models.SET_NULL, null=True, blank=True, related_name='dismissals')

    timestamp = models.DateTimeField(auto_now_add=True)

    def total_runs(self):
        return self.runs + self.extra_runs

    def __str__(self):
        return f"Over {self.over_number}.{self.ball_number} - {self.total_runs()} runs"
    def commentary(self):
        if self.is_wicket:
            return f"OUT! {self.player_out.name if self.player_out else self.batsman.name} is {self.get_wicket_type_display()} by {self.bowler.name}."
        if self.extra_type == 'wide':
            return f"{self.bowler.name} bowls a wide."
        if self.extra_type == 'noball':
            return f"No ball by {self.bowler.name}! {self.runs} run(s) off the bat too."
        if self.runs == 6:
            return f"SIX! {self.batsman.name} smashes it out of the park off {self.bowler.name}."
        if self.runs == 4:
            return f"FOUR! Beautiful shot by {self.batsman.name}."
        if self.runs == 0:
            return f"Dot ball. {self.bowler.name} to {self.batsman.name}, no run."
        return f"{self.batsman.name} takes {self.runs} run(s) off {self.bowler.name}."