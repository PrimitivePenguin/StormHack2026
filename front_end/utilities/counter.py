class Counter:
    def __init__(self, duration):
        self.duration = duration
        self.cur_time = 0
    
    def count(self):
        self.cur_time += 1
        if self.cur_time >= self.duration:
            self.cur_time = 0
            return True
        return False

    def reset(self):
        self.cur_time = 0