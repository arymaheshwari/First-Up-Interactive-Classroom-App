"""Socket.io event name constants."""

# Client → Server
JOIN_ROOM = "join_room"
REJOIN_ROOM = "rejoin_room"
HOST_ADVANCE = "host_advance"
HOST_LOCK_QUESTION = "host_lock_question"
SUBMIT_ANSWER = "submit_answer"
QUESTION_FEEDBACK = "question_feedback"  # a player's thumbs/flag on a shown question
HOST_SET_REACTIONS = "host_set_reactions"
PLAYER_REACTION = "player_reaction"

# Server → Client (broadcast to all in room)
NEW_QUESTION = "new_question"
QUESTION_RESULTS = "question_results"
GAME_OVER = "game_over"
PLAYER_JOINED = "player_joined"
PLAYER_LEFT = "player_left"
HOST_DISCONNECTED = "host_disconnected"
GAME_ABANDONED = "game_abandoned"

# Server → specific client
ANSWER_RECEIVED = "answer_received"
QUESTION_FEEDBACK_SAVED = "question_feedback_saved"
# Its own event, not ERROR: the player app treats ERROR as fatal to the game screen.
QUESTION_FEEDBACK_ERROR = "question_feedback_error"
REACTION_ERROR = "reaction_error"
SYNC_STATE = "sync_state"
ERROR = "error"

# Server → Host only
ANSWER_STATUS = "answer_status"
ANSWER_PHASE_ENDED = "answer_phase_ended"
REACTION_BUBBLE = "reaction_bubble"

# Server → all clients in room
QUESTION_LOCKED = "question_locked"
QUESTION_UNLOCKED = "question_unlocked"
REACTIONS_ENABLED = "reactions_enabled"
