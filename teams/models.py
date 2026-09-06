from django.db import models


class Team(models.Model):
    name = models.CharField(max_length=100, unique=True)
    short_name = models.CharField(max_length=10, help_text="e.g. TKM, MI, CSK")
    logo = models.ImageField(upload_to='team_logos/', blank=True, null=True)
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
    match_date = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')

    toss_winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='toss_wins')
    toss_decision = models.CharField(max_length=10, choices=TOSS_DECISION_CHOICES, blank=True)

    winner = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches_won')
    result_summary = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.team_a.short_name} vs {self.team_b.short_name} - {self.match_date.strftime('%d %b %Y')}"


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