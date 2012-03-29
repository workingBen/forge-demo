function getWeatherInfo(location, callback){
    forge.logging.log('[getWeatherInfo] getting weather for for '+location);
    forge.request.ajax({
        url:"http://www.google.com/ig/api?weather="+encodeURIComponent(location),
        dataType: 'xml',
        success: function(data, textStatus, jqXHR){
            forge.logging.log('[getWeatherInfo] success');
            var weatherObj = buildWeather(data);
            callback(weatherObj);
        },
        error: function(jqXHR, textStatus, errorThrown){
            forge.logging.log('ERROR! [getWeatherInfo] '+textStatus);
        }
    })
};

var xmlToJson = function(doc, keys) {
    /** Transforms an XML document into JSON

    doc is a document
    keys is an array of strings, specifying the names of XML nodes to pull from the document
    */
    var result = {};

    for (var counter=0; counter<keys.length; counter+=1) {
        result[keys[counter]] = $(keys[counter], doc).attr('data');
    }
    return result;
}

function formatImgSrc(imgURL) {
    return 'resources/'+/[a-z_]*.gif/.exec(imgURL)[0];
};

function buildForecastInformation(forecastInformation) {
    forge.logging.log('[buildForecastInformation] building internal forecast information object');

    return xmlToJson(forecastInformation, ['city', 'forecast_date']);
};

function buildCurrentCondition(currentCondition) {
    forge.logging.log('building current conditions object');

    var currentCondition = xmlToJson(currentCondition, ['condition', 'temp_f', 'humidity', 'icon', 'wind_condition']);
    currentCondition['icon'] = formatImgSrc(currentCondition['icon']);

    return currentCondition;
};

function buildForecastConditions(forecastConditions) {
    var convertedForecastConditions = [];
    $(forecastConditions).each(function(index, element) {
        convertedForecastConditions.push(buildForecastCondition(element));
    });
    return convertedForecastConditions;
};

function buildForecastCondition(forecastCondition) {
    forge.logging.log('[buildForecastCondition] building forecast condition');

    var forecastCondition = xmlToJson(forecastCondition, ['day_of_week', 'low', 'high', 'icon', 'condition']);
    forecastCondition['icon'] = formatImgSrc(forecastCondition['icon']);

    return forecastCondition;
};

function buildWeather(parsedData) {
    forge.logging.log('[buildWeather] converting data to internal representation');

    var forecastInformation = buildForecastInformation($('forecast_information', parsedData));
    var currentConditions = buildCurrentCondition($('current_conditions', parsedData))
    var forecastConditions = buildForecastConditions($('forecast_conditions', parsedData));

    return {
        forecast: forecastInformation,
        currentConditions: currentConditions,
        forecastConditions: forecastConditions
    }
};

function populateWeatherConditions(weatherCondition) {
    var tmpl, output;

    emptyContent();

    forge.logging.log('beginning populating weather conditions');

    tmpl = $('#forecast_information_tmpl').html();
    output = Mustache.to_html(tmpl, weatherCondition.forecast);
    $('#forecast_information').append(output);
    forge.logging.log('finished populating forecast information');
    
    tmpl = $('#current_conditions_tmpl').html();
    output = Mustache.to_html(tmpl, weatherCondition.currentConditions);
    $('#current_conditions').append(output);
    forge.logging.log('finished populating current conditions');
    
    tmpl = $('#forecast_conditions_tmpl').html();
    output = Mustache.to_html(tmpl, {conditions: weatherCondition.forecastConditions});
    $('#forecast_conditions table tr').append(output);
    forge.logging.log('finished populating forecast conditions');

    forge.logging.log('finished populating weather conditions');
};

function emptyContent(){
    forge.logging.log('removing old data');
    $('#forecast_information').empty();
    $('#current_conditions').empty();
    $('#forecast_conditions table tr').empty();

    forge.logging.log('finished emptying content');
};

// places I've been
var cities = ['San Francisco', 'Oakland', 'Boston', 'New York', 'Washington DC', 'Tampa', 'Houston', 'Montreal',
    'Los Angeles', 'Miami', 'West Palm Beach']; //and a few others

$(function(){
  //city population code
  cities.forEach(function(city){
      $('#city_menu').append('<option>'+city+'</option>');
  });
  $('#city_menu').change(function() {
      var city = $("#city_menu option:selected").html();
      forge.prefs.set('city', city);
      getWeatherInfo(city, populateWeatherConditions);
  });
  forge.prefs.get('city', function(resource) {
        if(resource) {
            if ($('#city_menu').val() == resource) {
                $('#city_menu').change();
            } else {
                //change event is not fired until focus is lost
                $('#city_menu').val(resource).change();
            }
        }
        else { //default
            getWeatherInfo('New York', populateWeatherConditions);
        }
    },
    function() {
        forge.logging.log('ERROR! failed when retrieving city preferences');
        $('#city_menu').val('New York'); //default;
    }
);
});
