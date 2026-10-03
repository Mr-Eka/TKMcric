from django import forms
from .models import Team, Player, Match, Innings, Ball


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name', 'short_name', 'logo']


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ['name', 'role', 'jersey_number', 'profile_picture']


class MatchForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ['team_a', 'team_b', 'overs_limit', 'match_date']
        widgets = {
            'match_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }


class TossForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = ['toss_winner', 'toss_decision']

    def __init__(self, *args, **kwargs):
        match = kwargs.pop('match', None)
        super().__init__(*args, **kwargs)
        if match:
            self.fields['toss_winner'].queryset = Team.objects.filter(pk__in=[match.team_a.pk, match.team_b.pk])


class InningsForm(forms.ModelForm):
    opener_striker = forms.ModelChoiceField(queryset=Player.objects.none())
    opener_non_striker = forms.ModelChoiceField(queryset=Player.objects.none())
    opening_bowler = forms.ModelChoiceField(queryset=Player.objects.none())

    class Meta:
        model = Innings
        fields = ['batting_team', 'bowling_team', 'innings_number']

    def __init__(self, *args, **kwargs):
        match = kwargs.pop('match', None)
        super().__init__(*args, **kwargs)
        if match:
            all_players = Player.objects.filter(team__in=[match.team_a, match.team_b])
            self.fields['opener_striker'].queryset = all_players
            self.fields['opener_non_striker'].queryset = all_players
            self.fields['opening_bowler'].queryset = all_players


class BallForm(forms.ModelForm):
    next_batsman = forms.ModelChoiceField(queryset=Player.objects.none(), required=False, help_text="Only needed if a wicket falls")

    class Meta:
        model = Ball
        fields = ['batsman', 'bowler', 'runs', 'extra_type', 'extra_runs', 'is_wicket', 'wicket_type', 'player_out']

    def __init__(self, *args, **kwargs):
        innings = kwargs.pop('innings', None)
        super().__init__(*args, **kwargs)
        if innings:
            self.fields['batsman'].queryset = innings.batting_team.players.all()
            self.fields['bowler'].queryset = innings.bowling_team.players.all()
            self.fields['player_out'].queryset = innings.batting_team.players.all()
            self.fields['next_batsman'].queryset = innings.batting_team.players.all()
            if innings.current_striker:
                self.fields['batsman'].initial = innings.current_striker.pk
            if innings.current_bowler:
                self.fields['bowler'].initial = innings.current_bowler.pk