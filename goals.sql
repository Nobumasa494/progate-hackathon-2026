-- goals テーブル作成（DBたたき台）
-- 1行 = 1回の目標設定。更新時はUPDATEせずINSERTで履歴を残す。
CREATE TABLE IF NOT EXISTS goals (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            uuid        NOT NULL REFERENCES auth.users (id),
    current_weight_kg  numeric(5,1) NOT NULL,
    target_weight_kg   numeric(5,1) NOT NULL,
    target_date        date        NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE goals IS '体重目標。更新のたびに1行INSERTし、最新行を現在の目標とする';

-- INSERT運用で最新goalを引くためのインデックス
CREATE INDEX IF NOT EXISTS idx_goals_user_id_created_at
    ON goals (user_id, created_at DESC);

-- RLS: 自分のgoalだけ見えるように（Supabase）
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "goals_select_own" ON goals
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "goals_insert_own" ON goals
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- 現在の目標を取得（全履歴から最新1件）
-- SELECT DISTINCT ON (user_id) *
-- FROM goals
-- WHERE user_id = auth.uid()
-- ORDER BY user_id, created_at DESC;