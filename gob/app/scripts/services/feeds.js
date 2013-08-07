'use strict';

angular.module('pourOver').factory('Feeds', ['$rootScope', 'ApiClient', function ($rootScope, ApiClient) {

  var DEFAULT_FEED_OBJ = {
    max_stories_per_period: 1,
    schedule_period: 1,
    format_mode: 1,
    include_thumb: true,
    include_video: true
  };

  $rootScope.feed = _.extend({}, DEFAULT_FEED_OBJ);
  $rootScope.feeds = [];
  var selected_feed = false;
  var new_feed = false;

  var updateFeeds = function () {
    ApiClient.get({
      url: 'feeds'
    }).success(function (resp) {
      if (resp.data && resp.data.length) {
        $rootScope.feeds = resp.data;
        console.log($rootScope.feeds);
        if (new_feed) {
          new_feed = false;
          return;
        }
        if (!selected_feed) {
          $rootScope.feed = resp.data[0];
        } else {
          _.each($rootScope.feeds, function (item) {
            if (item.feed_id === +selected_feed) {
              $rootScope.feed = item;
            }
          });
          selected_feed = false;
        }
      }
    });
  };

  updateFeeds();

  return {
    DEFAULT_FEED_OBJ: DEFAULT_FEED_OBJ,
    setFeed: function (feed_id) {
      selected_feed = feed_id;
      _.each($rootScope.feeds, function (item) {
        if (item.feed_id === +selected_feed) {
          $rootScope.feed = item;
        }
      });
    },
    setNewFeed: function () {
      new_feed = true;
      $rootScope.feed = _.extend({}, DEFAULT_FEED_OBJ);
    },
    deleteCurrentFeed: function () {
      var current_feed_id = $rootScope.feed.feed_id;
      $rootScope.feed = _.extend({}, DEFAULT_FEED_OBJ);
      $rootScope.feeds = _.filter($rootScope.feeds, function (item) {
        return item.feed_id !== current_feed_id;
      });
    },
    updateFeeds: updateFeeds
  };

}]);